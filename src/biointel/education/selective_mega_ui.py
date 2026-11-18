from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ._streamlit_compat import st
from .paths import education_paths
from .platform import EducationPlatform
from .selective_mega import CLASSWORK_TYPES, ENTITY_TYPES, QUESTION_TYPES, EducationMegaService

Run = Callable[[Callable[[], Any]], Any]


def _service(platform: Any, root: Path) -> EducationMegaService:
    return EducationMegaService(platform, root / "config" / "education_official_sources.json")


def _has(service: EducationMegaService, actor: str, institution_id: str, capability: str) -> bool:
    capabilities = service.capabilities(actor, institution_id)
    return "*" in capabilities or capability in capabilities


def _records(
    service: EducationMegaService, sql: str, args: tuple[Any, ...]
) -> list[dict[str, Any]]:
    return service._all(sql, args)


def render_education_launch_cards(
    root: Path, safe_page_link: Callable[[str, str | None], None]
) -> None:
    """Render three native, database-derived Education launch cards."""
    database_path, media_path = education_paths(root)
    try:
        platform = EducationPlatform(database_path, media_path)
        service = _service(platform, root)
        snapshot = service.module_snapshot()
        state, error = "Operational", ""
    except Exception as exc:
        snapshot = {
            "classes": 0,
            "pending_classwork": 0,
            "pending_workflows": 0,
            "exam_registrations": 0,
            "pending_evaluations": 0,
            "official_records": 0,
            "last_updated": None,
        }
        state, error = "Needs attention", str(exc)
    cards = [
        {
            "key": "biointel_education_home",
            "icon": ":material/account_balance:",
            "title": "Education Hub",
            "description": "Institution operations, people, services, governance and India-source provenance.",
            "status": state,
            "metric": snapshot["pending_workflows"],
            "metric_label": "pending approvals",
            "secondary": snapshot["official_records"],
            "secondary_label": "official records",
        },
        {
            "key": "biointel_classroom",
            "icon": ":material/co_present:",
            "title": "BioIntel Classroom",
            "description": "Teaching spaces, class stream, classwork, attendance, submissions and grading.",
            "status": state,
            "metric": snapshot["pending_classwork"],
            "metric_label": "active classwork",
            "secondary": snapshot["classes"],
            "secondary_label": "active classes",
        },
        {
            "key": "biointel_examinations",
            "icon": ":material/fact_check:",
            "title": "Examination Command Center",
            "description": "Secure delivery, registration, scheduling, evaluation and versioned results.",
            "status": state,
            "metric": snapshot["pending_evaluations"],
            "metric_label": "pending evaluations",
            "secondary": snapshot["exam_registrations"],
            "secondary_label": "registrations",
        },
    ]
    columns = st.columns(3, gap="medium")
    for column, card in zip(columns, cards):
        with column:
            with st.container(border=True):
                st.subheader(f"{card['icon']} {card['title']}")
                st.caption(card["description"])
                m1, m2 = st.columns(2)
                m1.metric(card["metric_label"].title(), int(card["metric"]))
                m2.metric(card["secondary_label"].title(), int(card["secondary"]))
                status_icon = (
                    ":material/check_circle:"
                    if card["status"] == "Operational"
                    else ":material/error:"
                )
                st.write(f"{status_icon} **{card['status']}**")
                last = snapshot.get("last_updated")
                st.caption(f"Last database activity: {last or 'No activity recorded yet'}")
                if error:
                    st.error(
                        "Education storage could not be read. Open the module for recovery details."
                    )
                    with st.expander("Technical detail"):
                        st.code(error)
                safe_page_link(card["key"], f"Open {card['title']}")
                st.page_link(
                    "pages/339_BioIntel_Education_Home.py",
                    label="Education help & status",
                    icon=":material/help:",
                )


def _snapshot_metrics(service: EducationMegaService, actor: str, institution_id: str) -> None:
    snapshot = service.module_snapshot(actor, institution_id)
    columns = st.columns(6)
    values = [
        ("Active classes", snapshot["classes"]),
        ("Active classwork", snapshot["pending_classwork"]),
        ("Pending approvals", snapshot["pending_workflows"]),
        ("Exam registrations", snapshot["exam_registrations"]),
        ("Evaluation drafts", snapshot["pending_evaluations"]),
        ("Directory records", snapshot["official_records"]),
    ]
    for column, (label, value) in zip(columns, values):
        column.metric(label, int(value))
    st.caption(f"Last database activity: {snapshot['last_updated'] or 'No activity recorded yet'}")


def _entity_workspace(
    service: EducationMegaService,
    actor: str,
    institution_id: str,
    run: Run,
    *,
    people: bool = False,
) -> None:
    types = (
        ["student", "staff", "admission_campaign", "admission_application", "service_request"]
        if people
        else sorted(
            ENTITY_TYPES
            - {"student", "staff", "admission_campaign", "admission_application", "service_request"}
        )
    )
    can_write = _has(service, actor, institution_id, "entities.write")
    if can_write:
        with st.form(
            f"mega-entity-create-{'people' if people else 'institution'}", clear_on_submit=True
        ):
            st.subheader(
                "Add institution record" if not people else "Add people or admissions record"
            )
            entity_type = st.selectbox(
                "Record type", types, format_func=lambda item: item.replace("_", " ").title()
            )
            c1, c2 = st.columns(2)
            name = c1.text_input("Name", placeholder="Required")
            code = c2.text_input(
                "Institution code", help="Optional, but unique within the selected record type."
            )
            details = st.text_area(
                "Structured details (JSON)",
                value="{}",
                help="Store configurable policy or profile fields without a destructive schema change.",
            )
            submitted = st.form_submit_button("Save record", type="primary", icon=":material/save:")
        if submitted:
            try:
                payload = json.loads(details or "{}")
                if not isinstance(payload, dict):
                    raise ValueError("Details must be a JSON object.")
            except ValueError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                result = run(
                    lambda: service.create_entity(
                        actor, institution_id, entity_type, name, code=code, data=payload
                    )
                )
                if result:
                    st.success("Record saved with an audit event.", icon=":material/check_circle:")
                    st.rerun()
    else:
        st.info("Your role has read-only access to institution records.", icon=":material/lock:")
    c1, c2 = st.columns([1, 2])
    selected_type = c1.selectbox(
        "Filter by type",
        ["All", *types],
        key=f"entity-type-{'people' if people else 'institution'}",
    )
    query = c2.text_input(
        "Search records",
        placeholder="Name or institution code",
        key=f"entity-search-{'people' if people else 'institution'}",
    )
    rows = (
        run(
            lambda: service.list_entities(
                actor, institution_id, "" if selected_type == "All" else selected_type, query
            )
        )
        or []
    )
    if rows:
        st.dataframe(
            [
                {
                    "Type": row["entity_type"].replace("_", " ").title(),
                    "Name": row["name"],
                    "Code": row["code"],
                    "State": row["state"],
                    "Updated": row["updated_at"],
                }
                for row in rows
            ],
            hide_index=True,
            width="stretch",
        )
        st.download_button(
            "Export visible records",
            data=service.export_csv(rows),
            file_name="biointel-education-records.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    else:
        st.info(
            "No matching records yet. Use the form above if your role can create one.",
            icon=":material/inbox:",
        )


def _services_workspace(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    caps = service.capabilities(actor, institution_id)
    if "*" in caps or "services.request" in caps:
        with st.form("mega-service-request", clear_on_submit=True):
            st.subheader("Student and staff services")
            request_type = st.selectbox(
                "Request type",
                [
                    "leave",
                    "attendance_correction",
                    "bonafide_certificate",
                    "migration_certificate",
                    "transcript",
                    "examination_form",
                    "re_evaluation",
                    "grievance",
                    "counselling",
                    "parent_teacher_meeting",
                ],
            )
            subject = st.text_input("Subject")
            detail = st.text_area("Request details")
            submitted = st.form_submit_button(
                "Submit request", type="primary", icon=":material/send:"
            )
        if submitted:
            result = run(
                lambda: service.create_workflow(
                    actor,
                    institution_id,
                    "service_request",
                    {"request_type": request_type, "subject": subject, "detail": detail},
                )
            )
            if result:
                st.success("Request submitted and routed to the institution queue.")
                st.rerun()
    queue = _records(
        service,
        "SELECT id,workflow_type,requester_id,state,decision_reason,created_at,updated_at FROM education_workflows WHERE institution_id=? ORDER BY updated_at DESC LIMIT 100",
        (institution_id,),
    )
    if queue:
        st.dataframe(queue, hide_index=True, width="stretch")
    else:
        st.info("No service or approval requests are visible yet.", icon=":material/inbox:")


def _official_source_catalog(coverage: dict[str, Any]) -> None:
    source_rows = coverage["sources"]
    imported = int(coverage["totals"]["imported"])
    with st.expander(
        f":material/account_balance: Official school & college sources ({len(source_rows)})",
        expanded=imported == 0,
    ):
        st.caption(
            "Production source catalogue. Each link opens the responsible government or regulatory authority; "
            "BioIntel displays institution records only after a lawful public or authorised import."
        )
        if source_rows:
            st.dataframe(
                [
                    {
                        "Source": row["name"],
                        "Covers": row["scope"],
                        "Authority": row["authority"],
                        "Records": int(row["imported"] or 0),
                        "Import status": row["last_success_at"]
                        or "Awaiting authorised dataset",
                        "Official website": row["url"],
                    }
                    for row in source_rows
                ],
                column_config={
                    "Official website": st.column_config.LinkColumn(
                        "Official website", display_text="Open source"
                    )
                },
                hide_index=True,
                width="stretch",
            )
        else:
            st.error(
                "The official Education source catalogue could not be loaded from configuration.",
                icon=":material/error:",
            )


def _official_directory_browser(
    service: EducationMegaService, coverage: dict[str, Any], run: Run
) -> None:
    st.subheader("Imported real school & college directory")
    source_rows = coverage["sources"]
    source_map = {row["id"]: row for row in source_rows}
    c1, c2 = st.columns([3, 2])
    query = c1.text_input(
        "Find an institution",
        placeholder="School, college, university, official code, state or district",
        key="education-official-directory-query",
    )
    selected_source = c2.selectbox(
        "Directory source",
        ["", *source_map],
        format_func=lambda key: "All official sources"
        if not key
        else source_map[key]["name"],
        key="education-official-directory-source",
    )
    rows = (
        run(
            lambda: service.list_directory_records(
                source_id=selected_source, query=query, limit=500
            )
        )
        or []
    )
    if rows:
        visible = [
            {
                "Institution": row["name"],
                "Type": row["institution_type"],
                "Official ID": row["official_id"],
                "State / UT": row["state_ut"],
                "District": row["district"],
                "Board": row["board"],
                "Recognition": row["recognition_status"],
                "Source": row["source_name"],
                "Dataset year": row["dataset_year"],
                "Retrieved": row["retrieved_at"],
                "Verification": row["verification_status"],
                "Official record": row["source_url"],
            }
            for row in rows
        ]
        st.dataframe(
            visible,
            column_config={
                "Official record": st.column_config.LinkColumn(
                    "Official record", display_text="Open evidence"
                )
            },
            hide_index=True,
            width="stretch",
        )
        st.download_button(
            "Export visible official records",
            data=service.export_csv(rows),
            file_name="biointel-official-institution-directory.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    elif int(coverage["totals"]["imported"]) == 0:
        st.info(
            f"{len(source_rows)} real official sources are registered, but no institution dataset has been "
            "imported yet. Use an authority-provided or institution-authorised CSV below; BioIntel will not "
            "invent school or college entries.",
            icon=":material/database:",
        )
    else:
        st.info(
            "No imported official institution matches these filters.",
            icon=":material/search_off:",
        )


def _india_data_workspace(
    service: EducationMegaService,
    actor: str,
    institution_id: str,
    run: Run,
    coverage: dict[str, Any] | None = None,
) -> None:
    coverage = coverage or service.directory_coverage()
    totals = coverage["totals"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Imported", totals["imported"])
    c2.metric("Verified", totals["verified"])
    c3.metric("Pending review", totals["pending"])
    c4.metric("Conflicts", totals["conflicts"])
    st.warning(
        "Coverage is partial and import-driven. Source presence is not automatically a current recognition decision.",
        icon=":material/info:",
    )
    source_rows = coverage["sources"]
    _official_directory_browser(service, coverage, run)
    if _has(service, actor, institution_id, "directory.import"):
        source_map = {row["id"]: row for row in source_rows}
        with st.form("mega-official-import", clear_on_submit=False):
            st.subheader("Authorised official-directory import")
            source_id = st.selectbox(
                "Official source", list(source_map), format_func=lambda key: source_map[key]["name"]
            )
            dataset_year = st.text_input("Dataset year", placeholder="For example, 2025-26")
            upload = st.file_uploader(
                "UTF-8 CSV",
                type=["csv"],
                help="Public or institution-authorised institution records only. Private student or teacher fields are rejected.",
            )
            confirmed = st.checkbox(
                "I confirm this file is lawfully obtained and contains no private student or teacher records."
            )
            submitted = st.form_submit_button(
                "Validate and import",
                type="primary",
                icon=":material/publish:",
                disabled=upload is None or not confirmed,
            )
        if submitted and upload:
            result = run(
                lambda: service.import_csv(
                    actor, institution_id, source_id, upload.getvalue(), dataset_year=dataset_year
                )
            )
            if result:
                st.success(
                    f"Import completed: {result['records_imported']} imported, {result['records_rejected']} rejected."
                )
                st.rerun()
    else:
        st.info(
            "Official-directory import requires registrar or institution-administrator permission.",
            icon=":material/lock:",
        )


def _search_workspace(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    st.subheader("Education search")
    st.caption(
        "Press Ctrl+K in the app to focus Streamlit navigation; this permission-aware search covers the selected education data."
    )
    c1, c2 = st.columns([3, 1])
    query = c1.text_input(
        "Search",
        placeholder="Institution, campus, department, programme, class or code",
        key="education-mega-search",
    )
    category = c2.selectbox("Category", ["All", "Institution", "Entity", "Classroom"])
    rows = (
        run(
            lambda: service.search(
                actor, institution_id, query, category="" if category == "All" else category.lower()
            )
        )
        if query
        else []
    )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    elif query:
        st.info(
            "No results. Check spelling or create the missing record if your role allows it.",
            icon=":material/search_off:",
        )


def render_education_hub_mega(
    platform: Any, actor: str, institution_id: str, root: Path, run: Run
) -> None:
    service = _service(platform, root)
    _snapshot_metrics(service, actor, institution_id)
    coverage = service.directory_coverage()
    _official_source_catalog(coverage)
    view = st.segmented_control(
        "Education Hub workspace",
        [
            "Command centre",
            "Institution",
            "People & admissions",
            "Services",
            "India data",
            "Search",
        ],
        default="Command centre",
        key=f"education-mega-hub-{actor}-{institution_id}",
    )
    if view == "Command centre":
        from .home_ui import render_education_home_workspace

        render_education_home_workspace(platform, actor, institution_id, run)
    elif view == "Institution":
        _entity_workspace(service, actor, institution_id, run)
    elif view == "People & admissions":
        _entity_workspace(service, actor, institution_id, run, people=True)
    elif view == "Services":
        _services_workspace(service, actor, institution_id, run)
    elif view == "India data":
        _india_data_workspace(service, actor, institution_id, run, coverage)
    else:
        _search_workspace(service, actor, institution_id, run)


def _class_rows(
    service: EducationMegaService, actor: str, institution_id: str
) -> list[dict[str, Any]]:
    caps = service.capabilities(actor, institution_id)
    if "*" in caps or "classroom.manage" in caps:
        return _records(
            service,
            "SELECT * FROM education_classes_r9 WHERE institution_id=? ORDER BY updated_at DESC",
            (institution_id,),
        )
    return _records(
        service,
        """SELECT c.* FROM education_classes_r9 c JOIN education_class_members_r9 m ON m.class_id=c.id
        WHERE c.institution_id=? AND m.user_id=? AND m.state='active' ORDER BY c.updated_at DESC""",
        (institution_id, actor),
    )


def _classroom_manage(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    can_manage = _has(service, actor, institution_id, "classroom.manage")
    if can_manage:
        with st.form("mega-class-create", clear_on_submit=True):
            st.subheader("Create a controlled class")
            c1, c2 = st.columns(2)
            name = c1.text_input("Class name", placeholder="Molecular Biology 202")
            class_code = c2.text_input("Unique class code", placeholder="MBIO-2026")
            c3, c4, c5 = st.columns(3)
            section = c3.text_input("Section")
            session = c4.text_input("Academic session")
            visibility = c5.selectbox("Joining policy", ["institution", "private", "code"])
            meeting = st.text_input(
                "Meeting-link adapter", placeholder="Optional configured provider URL"
            )
            submitted = st.form_submit_button(
                "Create class", type="primary", icon=":material/add_circle:"
            )
        if submitted:
            result = run(
                lambda: service.create_class(
                    actor,
                    institution_id,
                    name,
                    class_code,
                    section=section,
                    academic_session=session,
                    visibility=visibility,
                    meeting_url=meeting,
                )
            )
            if result:
                st.success("Class created; the class code is unique and permission controlled.")
                st.rerun()
    classes = _class_rows(service, actor, institution_id)
    if not classes:
        st.info(
            "No classes are visible. An authorised educator can create the first class above.",
            icon=":material/co_present:",
        )
        return
    class_map = {row["id"]: row for row in classes}
    selected = st.selectbox(
        "Class workspace",
        list(class_map),
        format_func=lambda key: f"{class_map[key]['name']} ? {class_map[key]['class_code']}",
        key="mega-class-selected",
    )
    classroom = class_map[selected]
    c1, c2, c3 = st.columns(3)
    c1.metric("Class code", classroom["class_code"])
    c2.metric("State", classroom["state"].title())
    c3.metric("Visibility", classroom["visibility"].title())
    if can_manage:
        with st.form("mega-class-invite", clear_on_submit=True):
            st.subheader("Invite member")
            c4, c5 = st.columns(2)
            user_id = c4.text_input("Education user ID")
            role = c5.selectbox("Class role", ["student", "co_teacher", "teacher"])
            invite = st.form_submit_button("Send invitation", icon=":material/person_add:")
        if invite:
            result = run(
                lambda: service.invite_class_member(actor, institution_id, selected, user_id, role)
            )
            if result:
                st.success("Invitation persisted and an in-app notification was created.")
                st.rerun()
        with st.form("mega-stream-post", clear_on_submit=True):
            st.subheader("Publish to class stream")
            title = st.text_input("Post title")
            body = st.text_area("Announcement")
            c6, c7 = st.columns(2)
            pinned = c6.checkbox("Pin this post")
            scheduled = c7.text_input("Schedule at (ISO-8601)", placeholder="Blank publishes now")
            publish = st.form_submit_button(
                "Publish or schedule", type="primary", icon=":material/campaign:"
            )
        if publish:
            result = run(
                lambda: service.add_stream_post(
                    actor,
                    institution_id,
                    selected,
                    body,
                    title=title,
                    scheduled_at=scheduled or None,
                    pinned=pinned,
                )
            )
            if result:
                st.success("Stream post saved.")
                st.rerun()
    posts = _records(
        service,
        "SELECT title,body,author_id,pinned,edited,moderation_state,scheduled_at,published_at,created_at FROM education_stream_posts_r9 WHERE class_id=? AND state='active' ORDER BY pinned DESC,created_at DESC",
        (selected,),
    )
    st.subheader("Class stream")
    if posts:
        for post in posts:
            with st.container(border=True):
                st.markdown(f"**{post['title'] or 'Announcement'}**")
                st.write(post["body"])
                st.caption(
                    f"By {post['author_id']} ? {post['published_at'] or 'Scheduled for ' + str(post['scheduled_at'])} ? Moderation: {post['moderation_state']}"
                )
    else:
        st.info(
            "The stream is empty. A teacher can publish the first announcement.",
            icon=":material/dynamic_feed:",
        )


def _classwork_manage(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    classes = _class_rows(service, actor, institution_id)
    if not classes:
        st.info("Create or join a class before using classwork.", icon=":material/inbox:")
        return
    class_map = {row["id"]: row for row in classes}
    selected = st.selectbox(
        "Class",
        list(class_map),
        format_func=lambda key: class_map[key]["name"],
        key="mega-classwork-class",
    )
    can_manage = _has(service, actor, institution_id, "classroom.manage")
    if can_manage:
        with st.form("mega-classwork-create", clear_on_submit=True):
            st.subheader("Create classwork")
            c1, c2 = st.columns(2)
            item_type = c1.selectbox(
                "Classwork type",
                sorted(CLASSWORK_TYPES),
                format_func=lambda item: item.replace("_", " ").title(),
            )
            title = c2.text_input("Title")
            instructions = st.text_area("Instructions")
            c3, c4, c5 = st.columns(3)
            topic = c3.text_input("Topic or unit")
            due_at = c4.text_input("Due at (ISO-8601)", placeholder="Optional")
            marks = c5.number_input("Maximum marks", min_value=0.0, value=0.0)
            state = st.segmented_control(
                "Publication state", ["draft", "scheduled", "published"], default="draft"
            )
            submitted = st.form_submit_button(
                "Save classwork", type="primary", icon=":material/assignment_add:"
            )
        if submitted:
            result = run(
                lambda: service.create_classwork(
                    actor,
                    institution_id,
                    selected,
                    item_type,
                    title,
                    instructions=instructions,
                    topic=topic,
                    due_at=due_at or None,
                    max_marks=marks,
                    state=state or "draft",
                )
            )
            if result:
                st.success("Classwork saved and audited.")
                st.rerun()
    rows = _records(
        service,
        "SELECT item_type,title,topic,due_at,max_marks,state,updated_at FROM education_classwork_r9 WHERE class_id=? ORDER BY due_at,updated_at DESC",
        (selected,),
    )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
        st.download_button(
            "Export classwork",
            service.export_csv(rows),
            file_name="biointel-classwork.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    else:
        st.info("No classwork has been created for this class.", icon=":material/assignment:")


def render_classroom_mega(
    platform: Any, actor: str, institution_id: str, root: Path, run: Run
) -> None:
    service = _service(platform, root)
    snapshot = service.module_snapshot(actor, institution_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active classes", snapshot["classes"])
    c2.metric("Active classwork", snapshot["pending_classwork"])
    c3.metric("Unread alerts", snapshot["unread_notifications"])
    c4.metric("Last activity", snapshot["last_updated"] or "None")
    view = st.selectbox(
        "Classroom workspace",
        ["Visual intelligence", "Operations", "Classes & stream", "Classwork", "Shiro tutor", "Search"],
        key=f"education-mega-classroom-{actor}-{institution_id}",
    )
    if view == "Visual intelligence":
        from .phase2 import EducationPhase2
        from .phase2_ui import render_classroom_visuals

        render_classroom_visuals(EducationPhase2(platform), actor, institution_id, run)
    elif view == "Operations":
        from .classroom_ui import render_classroom_workspace

        render_classroom_workspace(platform, actor, institution_id, run)
    elif view == "Classes & stream":
        _classroom_manage(service, actor, institution_id, run)
    elif view == "Classwork":
        _classwork_manage(service, actor, institution_id, run)
    elif view == "Shiro tutor":
        from .intelligence_ui import render_shiro_course_tutor

        render_shiro_course_tutor(platform, root, actor, institution_id)
    else:
        _search_workspace(service, actor, institution_id, run)


def _exam_registration(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    caps = service.capabilities(actor, institution_id)
    if "*" in caps or "exam.registration" in caps:
        with st.form("mega-exam-registration", clear_on_submit=True):
            st.subheader("Examination registration")
            examination_id = st.text_input("Examination ID")
            subjects = st.text_input("Subject IDs", placeholder="Comma-separated")
            eligibility_confirmed = st.checkbox(
                "I confirm the supplied registration details are accurate."
            )
            submitted = st.form_submit_button(
                "Submit examination form",
                type="primary",
                icon=":material/app_registration:",
                disabled=not eligibility_confirmed,
            )
        if submitted:
            result = run(
                lambda: service.register_exam(
                    actor,
                    institution_id,
                    examination_id,
                    [item.strip() for item in subjects.split(",") if item.strip()],
                    {"applicant_confirmed": True},
                )
            )
            if result:
                st.success(f"Registration submitted: {result['registration_number']}")
                st.rerun()
    if "*" in caps or "exam.manage" in caps:
        registrations = _records(
            service,
            "SELECT * FROM education_exam_registrations_r9 WHERE institution_id=? ORDER BY updated_at DESC",
            (institution_id,),
        )
    else:
        registrations = _records(
            service,
            "SELECT * FROM education_exam_registrations_r9 WHERE institution_id=? AND student_id=? ORDER BY updated_at DESC",
            (institution_id, actor),
        )
    if registrations:
        st.dataframe(
            [
                {
                    key: row[key]
                    for key in (
                        "id",
                        "examination_id",
                        "student_id",
                        "registration_number",
                        "state",
                        "decision_reason",
                        "updated_at",
                    )
                }
                for row in registrations
            ],
            hide_index=True,
            width="stretch",
        )
    if registrations and ("*" in caps or "exam.manage" in caps):
        pending = [row for row in registrations if row["state"] == "submitted"]
        if pending:
            pending_map = {row["id"]: row for row in pending}
            with st.form("mega-exam-registration-decision"):
                selected = st.selectbox(
                    "Pending registration",
                    list(pending_map),
                    format_func=lambda key: (
                        f"{pending_map[key]['registration_number']} ? {pending_map[key]['student_id']}"
                    ),
                )
                decision = st.segmented_control(
                    "Decision", ["Approve", "Reject"], default="Approve"
                )
                reason = st.text_input("Decision reason", help="Required when rejecting.")
                decide = st.form_submit_button(
                    "Record decision", type="primary", icon=":material/gavel:"
                )
            if decide:
                result = run(
                    lambda: service.decide_exam_registration(
                        actor, institution_id, selected, decision == "Approve", reason
                    )
                )
                if result:
                    st.success("Registration decision saved and the student was notified.")
                    st.rerun()


def _question_bank(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    if _has(service, actor, institution_id, "exam.author"):
        with st.form("mega-question-bank", clear_on_submit=True):
            st.subheader("Question bank")
            c1, c2 = st.columns(2)
            subject_id = c1.text_input("Subject ID")
            question_type = c2.selectbox(
                "Question type",
                sorted(QUESTION_TYPES),
                format_func=lambda item: item.replace("_", " ").title(),
            )
            prompt = st.text_area("Question text")
            answer = st.text_area(
                "Answer key or evaluation guide", help="Restricted to authorised examination roles."
            )
            tags = st.text_input("Tags", placeholder="Comma-separated")
            submitted = st.form_submit_button(
                "Save draft question", type="primary", icon=":material/library_add:"
            )
        if submitted:
            result = run(
                lambda: service.add_question(
                    actor,
                    institution_id,
                    subject_id,
                    question_type,
                    prompt,
                    answer={"guide": answer},
                    metadata={"tags": [item.strip() for item in tags.split(",") if item.strip()]},
                )
            )
            if result:
                st.success("Question saved; duplicate fingerprint checks passed.")
                st.rerun()
    can_view_bank = (
        _has(service, actor, institution_id, "exam.author")
        or _has(service, actor, institution_id, "exam.manage")
        or _has(service, actor, institution_id, "exam.evaluate")
    )
    rows = (
        _records(
            service,
            "SELECT id,subject_id,question_type,prompt,version,state,author_id,updated_at FROM education_question_bank_r9 WHERE institution_id=? ORDER BY updated_at DESC LIMIT 100",
            (institution_id,),
        )
        if can_view_bank
        else []
    )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("The authorised question bank has no entries.", icon=":material/quiz:")


def _exam_schedule(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    if _has(service, actor, institution_id, "exam.manage"):
        with st.form("mega-exam-schedule", clear_on_submit=True):
            st.subheader("Schedule examination")
            c1, c2 = st.columns(2)
            examination_id = c1.text_input("Examination ID")
            subject_id = c2.text_input("Subject ID")
            c3, c4 = st.columns(2)
            starts_at = c3.text_input(
                "Starts at (ISO-8601)", placeholder="2026-09-01T09:00:00+05:30"
            )
            ends_at = c4.text_input("Ends at (ISO-8601)", placeholder="2026-09-01T12:00:00+05:30")
            c5, c6 = st.columns(2)
            room = c5.text_input("Room")
            capacity = c6.number_input("Room capacity", min_value=1, value=30)
            invigilators = st.text_input("Invigilator IDs", placeholder="Comma-separated")
            submitted = st.form_submit_button(
                "Check conflicts and save", type="primary", icon=":material/event_available:"
            )
        if submitted:
            result = run(
                lambda: service.schedule_exam(
                    actor,
                    institution_id,
                    examination_id,
                    room,
                    int(capacity),
                    starts_at,
                    ends_at,
                    subject_id=subject_id,
                    invigilators=[item.strip() for item in invigilators.split(",") if item.strip()],
                )
            )
            if result:
                st.success(
                    "Schedule saved; overlapping room and invigilator conflicts were checked."
                )
                st.rerun()
    can_view_drafts = _has(service, actor, institution_id, "exam.manage") or _has(
        service, actor, institution_id, "exam.invigilate"
    )
    rows = (
        _records(
            service,
            "SELECT * FROM education_exam_schedules_r9 WHERE institution_id=? ORDER BY starts_at",
            (institution_id,),
        )
        if can_view_drafts
        else []
    )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No R9 examination schedules are stored.", icon=":material/event_busy:")


def _evaluation_results(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    if _has(service, actor, institution_id, "exam.evaluate"):
        with st.form("mega-evaluation", clear_on_submit=True):
            st.subheader("Marks entry and evaluation")
            c1, c2 = st.columns(2)
            examination_id = c1.text_input("Examination ID")
            student_id = c2.text_input("Student ID")
            marks_text = st.text_area("Question-wise marks (JSON)", value='{"Q1": 0, "Q2": 0}')
            submit = st.checkbox("Submit and lock this evaluator entry")
            saved = st.form_submit_button("Save evaluation", type="primary", icon=":material/save:")
        if saved:
            try:
                marks = json.loads(marks_text)
                if not isinstance(marks, dict):
                    raise ValueError("Marks must be a JSON object.")
            except (ValueError, json.JSONDecodeError) as exc:
                st.error(str(exc))
            else:
                result = run(
                    lambda: service.save_evaluation(
                        actor, institution_id, examination_id, student_id, marks, submit=submit
                    )
                )
                if result:
                    st.success("Evaluation saved with a complete audit event.")
                    st.rerun()
    if _has(service, actor, institution_id, "exam.publish"):
        with st.form("mega-result-process", clear_on_submit=True):
            st.subheader("Configurable result processing")
            c3, c4 = st.columns(2)
            result_exam = c3.text_input("Examination ID", key="result-exam")
            result_student = c4.text_input("Student ID", key="result-student")
            c5, c6, c7 = st.columns(3)
            total = c5.number_input("Marks obtained", min_value=0.0)
            maximum = c6.number_input("Maximum marks", min_value=1.0, value=100.0)
            pass_percentage = c7.number_input(
                "Pass percentage", min_value=0.0, max_value=100.0, value=40.0
            )
            publish = st.checkbox("Publish this version")
            processed = st.form_submit_button(
                "Create result version", type="primary", icon=":material/publish:"
            )
        if processed:
            rules = {
                "maximum_marks": maximum,
                "pass_percentage": pass_percentage,
                "grade_boundaries": [
                    {"minimum": 80, "grade": "A"},
                    {"minimum": 60, "grade": "B"},
                    {"minimum": 40, "grade": "C"},
                    {"minimum": 0, "grade": "F"},
                ],
            }
            result = run(
                lambda: service.process_result(
                    actor,
                    institution_id,
                    result_exam,
                    result_student,
                    total,
                    rules,
                    publish=publish,
                )
            )
            if result:
                st.success(f"Result version {result['version']} created.")
                st.rerun()
    can_view_all_results = _has(service, actor, institution_id, "exam.publish") or _has(
        service, actor, institution_id, "exam.evaluate"
    )
    if can_view_all_results:
        rows = _records(
            service,
            "SELECT id,examination_id,student_id,version,result_json,published,withdrawn,created_at FROM education_result_versions_r9 WHERE institution_id=? ORDER BY created_at DESC LIMIT 100",
            (institution_id,),
        )
    else:
        rows = _records(
            service,
            "SELECT id,examination_id,student_id,version,result_json,published,withdrawn,created_at FROM education_result_versions_r9 WHERE institution_id=? AND student_id=? AND published=1 AND withdrawn=0 ORDER BY created_at DESC LIMIT 100",
            (institution_id, actor),
        )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
        st.download_button(
            "Export result versions",
            service.export_csv(rows),
            file_name="biointel-result-versions.csv",
            mime="text/csv",
            icon=":material/download:",
        )


def _proctor_privacy(
    service: EducationMegaService, actor: str, institution_id: str, run: Run
) -> None:
    st.info(
        "Proctoring is optional and disabled by default. Signals are review cues, never proof of misconduct.",
        icon=":material/privacy_tip:",
    )
    if _has(service, actor, institution_id, "exam.proctor"):
        with st.form("mega-proctor-policy"):
            examination_id = st.text_input("Examination ID")
            enabled = st.toggle("Enable consent-based proctoring", value=False)
            provider = st.text_input("Configured provider adapter")
            c1, c2, c3 = st.columns(3)
            camera = c1.checkbox("Optional camera adapter")
            microphone = c2.checkbox("Optional microphone adapter")
            retention = c3.number_input("Retention days", min_value=0, max_value=3650, value=0)
            consent = st.text_area(
                "Transparent consent text", help="Required before the policy can be enabled."
            )
            saved = st.form_submit_button(
                "Save privacy policy", type="primary", icon=":material/policy:"
            )
        if saved:
            result = run(
                lambda: service.set_proctor_policy(
                    actor,
                    institution_id,
                    examination_id,
                    enabled=enabled,
                    provider=provider,
                    camera=camera,
                    microphone=microphone,
                    retention_days=int(retention),
                    consent_text=consent,
                )
            )
            if result:
                st.success("Proctoring privacy policy saved.")
                st.rerun()
    rows = _records(
        service,
        "SELECT examination_id,enabled,provider,camera,microphone,retention_days,updated_by,updated_at FROM education_proctor_policies_r9 WHERE institution_id=? ORDER BY updated_at DESC",
        (institution_id,),
    )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")


def render_examination_mega(
    platform: Any, actor: str, institution_id: str, root: Path, run: Run
) -> None:
    service = _service(platform, root)
    snapshot = service.module_snapshot(actor, institution_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registrations", snapshot["exam_registrations"])
    c2.metric("Evaluation drafts", snapshot["pending_evaluations"])
    c3.metric("Unread alerts", snapshot["unread_notifications"])
    c4.metric("Last activity", snapshot["last_updated"] or "None")
    view = st.segmented_control(
        "Examination lifecycle",
        [
            "Secure delivery",
            "Registration",
            "Question bank",
            "Scheduling",
            "Evaluation & results",
            "Privacy & proctoring",
        ],
        default="Secure delivery",
        key=f"education-mega-exam-{actor}-{institution_id}",
    )
    if view == "Secure delivery":
        from .examination_ui import render_examination_workspace

        render_examination_workspace(platform, actor, institution_id, run)
    elif view == "Registration":
        _exam_registration(service, actor, institution_id, run)
    elif view == "Question bank":
        _question_bank(service, actor, institution_id, run)
    elif view == "Scheduling":
        _exam_schedule(service, actor, institution_id, run)
    elif view == "Evaluation & results":
        _evaluation_results(service, actor, institution_id, run)
    else:
        _proctor_privacy(service, actor, institution_id, run)
