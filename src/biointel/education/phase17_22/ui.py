from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from ..paths import education_paths
from ..platform import EducationError, EducationPlatform
from .service import EducationOS


@st.cache_resource(show_spinner=False)
def _service(root_text: str, demo: bool) -> EducationOS:
    database, media = education_paths(root_text, demo=demo)
    platform = EducationPlatform(database, media)
    return EducationOS(platform, root=Path(root_text))


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except EducationError as exc:
        st.error(str(exc), icon=":material/error:")
        return None


def render_studio_education_workspace(root: Path) -> None:
    st.divider()
    st.header("Education & scientific content production", anchor=False)
    st.caption(
        "Persistent, tenant-scoped presentations, posters, reports, diagrams and lecture assets with versions, citations, human review and governed publication."
    )
    demo = bool(st.session_state.get("education_demo_mode", False))
    service = _service(str(root), demo)
    actor = str(st.session_state.get("education_actor") or "local-operator")
    memberships = service.platform._all(
        """SELECT DISTINCT i.id,i.name FROM institutions i JOIN memberships m ON m.institution_id=i.id
        WHERE m.user_id=? AND m.state='active' AND i.state='active' ORDER BY i.name""",
        (actor,),
    )
    if not memberships:
        st.info(
            "Open BioIntel Education Home first to select an authenticated or isolated demo identity with an institution workspace.",
            icon=":material/domain:",
        )
        try:
            st.page_link("pages/339_BioIntel_Education_Home.py", label="Open Education Home", icon=":material/dashboard:")
        except (KeyError, RuntimeError, TypeError):
            pass
        return
    by_id = {row["id"]: row for row in memberships}
    institution_id = st.selectbox(
        "Studio institution", list(by_id), format_func=lambda value: by_id[value]["name"],
        key="studio-education-institution",
    )
    projects = service.platform._all(
        """SELECT * FROM education_studio_projects WHERE institution_id=?
        AND (owner_id=? OR ? IN (SELECT user_id FROM memberships WHERE institution_id=? AND role IN
        ('platform_administrator','institution_administrator','principal','dean','department_head')))
        ORDER BY updated_at DESC""",
        (institution_id, actor, actor, institution_id),
    )
    create_view, work_view, capability_view = st.tabs(["Create", "Workspace", "Export capabilities"])
    with create_view:
        with st.form("studio-education-create"):
            title = st.text_input("Project title")
            project_type = st.selectbox(
                "Project type", ["presentation", "poster", "report", "diagram", "flowchart", "concept_map", "lecture_asset"]
            )
            description = st.text_area("Description")
            submitted = st.form_submit_button("Create persistent project", type="primary", icon=":material/add:")
        if submitted:
            created = _run(lambda: service.create_studio_project(
                actor, institution_id, title=title, project_type=project_type, description=description
            ))
            if created:
                st.success(f"Project created: {created['id']}")
                st.rerun()
    with work_view:
        if not projects:
            st.info("No Studio project is visible in this institution.")
        else:
            project_by_id = {row["id"]: row for row in projects}
            project_id = st.selectbox(
                "Project", list(project_by_id),
                format_func=lambda value: f"{project_by_id[value]['title']} · {project_by_id[value]['state']}",
                key="studio-education-project",
            )
            project = project_by_id[project_id]
            c1, c2, c3 = st.columns(3)
            c1.metric("State", str(project["state"]).replace("_", " ").title())
            c2.metric("Current version", int(project["current_version"]))
            c3.metric("Type", str(project["project_type"]).replace("_", " ").title())
            with st.form(f"studio-version-{project_id}"):
                default_content = {"title": project["title"], "sections": [], "notes": ""}
                content_text = st.text_area(
                    "Structured project JSON", value=json.dumps(default_content, indent=2), height=280,
                    help="Autosave-friendly structured content; binary media belongs in the governed asset library.",
                )
                change_note = st.text_input("Version note")
                save = st.form_submit_button("Save immutable version", type="primary", icon=":material/save:")
            if save:
                try:
                    content = json.loads(content_text)
                    if not isinstance(content, dict):
                        raise ValueError("Top-level Studio content must be an object.")
                except (ValueError, json.JSONDecodeError) as exc:
                    st.error(f"Invalid project JSON: {exc}")
                else:
                    saved = _run(lambda: service.save_studio_version(
                        actor, project_id, content, expected_version=int(project["current_version"]), change_note=change_note
                    ))
                    if saved:
                        st.success(f"Saved version {saved['version_number']} with SHA-256 {saved['content_sha256'][:16]}…")
                        st.rerun()
            with st.container(horizontal=True):
                if st.button("Submit for review", key=f"studio-submit-{project_id}", icon=":material/rate_review:"):
                    if _run(lambda: service.submit_studio_review(actor, project_id)):
                        st.rerun()
                if project["state"] == "review" and st.button(
                    "Approve", key=f"studio-approve-{project_id}", icon=":material/check_circle:"
                ):
                    if _run(lambda: service.review_studio_project(actor, project_id, decision="approved")):
                        st.rerun()
                if st.button("Export project bundle", key=f"studio-export-{project_id}", icon=":material/archive:"):
                    exported = _run(lambda: service.export_studio_bundle(actor, project_id))
                    if exported:
                        st.success(f"Verified bundle created · {exported['size_bytes']:,} bytes · SHA-256 {exported['sha256']}")
                        st.code(exported["path"])
            if project["state"] == "approved":
                with st.form(f"studio-publish-{project_id}"):
                    target_type = st.selectbox("Publish target", ["connect", "classroom", "academy"])
                    target_id = st.text_input("Target ID", value="institution-feed" if target_type == "connect" else "")
                    publish = st.form_submit_button("Queue governed publication", icon=":material/publish:")
                if publish:
                    publication = _run(lambda: service.publish_studio_project(
                        actor, project_id, target_type=target_type, target_id=target_id
                    ))
                    if publication:
                        st.success(f"Publication queued with durable outbox record: {publication['id']}")
                        st.rerun()
    with capability_view:
        rows = [
            {"Format": name, "Available": value["available"], "Verified locally": value["verified_locally"],
             "Boundary": value.get("reason", "Local structured export verified.")}
            for name, value in service.studio_capabilities().items()
        ]
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption("Unavailable formats are reported honestly; the UI never presents a fake download.")
