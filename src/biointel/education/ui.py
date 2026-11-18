from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from ._streamlit_compat import st

from .paths import education_paths
from .platform import ADMIN, EducationError, EducationPlatform
from .universe import EducationUniverse
from .experience import render_app_header, render_role_snapshot, render_workspace_context


@lru_cache(maxsize=8)
def _platform(root_text: str, demo: bool = False) -> EducationPlatform:
    database_path, media_path = education_paths(root_text, demo=demo)
    return EducationPlatform(database_path, media_path)


def _safe_identifier(value: Any, fallback: str = "") -> str:
    if callable(value):
        return fallback
    text = str(value or "").strip()
    if not text or text.startswith("<function") or len(text) > 240:
        return fallback
    return text


def _actor() -> str:
    return _safe_identifier(st.session_state.get("education_actor", "local-operator"), "local-operator")


def _run(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except EducationError as exc:
        st.error(str(exc), icon=":material/error:")
        return None


def _demo_run(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as exc:
        st.error(f"Demo workspace action failed: {exc}", icon=":material/error:")
        return None


def _header(title: str, subtitle: str, page_key: str) -> None:
    render_app_header(page_key, title, subtitle)


def _activate_demo(root: Path, seed: bool = True) -> bool:
    from .demo import manifest, seed_demo

    result = _demo_run(lambda: seed_demo(root) if seed else manifest(root))
    if not result:
        return False
    personas = result.get("personas", [])
    institutions = result.get("institutions", [])
    if not personas or not institutions:
        st.error("The demo manifest has no institutions or personas.", icon=":material/error:")
        return False
    persona = personas[0]
    st.session_state.education_demo_mode = True
    st.session_state.education_demo_institution_picker = persona["institution_id"]
    st.session_state.education_demo_persona_picker = persona["id"]
    st.session_state.education_institution = persona["institution_id"]
    st.session_state.education_actor = persona["id"]
    st.session_state.education_show_demo_manifest = False
    _platform.cache_clear()
    st.rerun()
    return True


def _exit_demo() -> None:
    st.session_state.education_demo_mode = False
    st.session_state.education_actor = "local-operator"
    st.session_state.education_institution = ""
    for key in (
        "education_demo_institution_picker",
        "education_demo_persona_picker",
        "education_institution_picker",
    ):
        st.session_state.pop(key, None)
    _platform.cache_clear()
    st.rerun()


def _demo_controls(root: Path) -> bool:
    from .demo import DEMO_BADGE, manifest, reset_demo, seed_demo

    if st.session_state.get("education_presentation_mode", False):
        with st.container(border=True):
            st.warning(DEMO_BADGE, icon=":material/science:")
            st.badge("PRESENTATION MODE", icon=":material/slideshow:", color="violet")
        return True

    demo_mode = bool(st.session_state.get("education_demo_mode", False))
    with st.container(border=True):
        left, right = st.columns([2.4, 1], vertical_alignment="center")
        if demo_mode:
            left.subheader(":material/science: Education demonstration workspace")
            left.caption(DEMO_BADGE)
            right.badge("DEMO", icon=":material/science:", color="violet")
        else:
            left.subheader(":material/science: Education demo controls")
            left.caption("Load an isolated, deterministic workspace without mixing synthetic records into institutional data.")
            right.badge("Real workspace", icon=":material/shield:", color="green")

        if not demo_mode:
            if st.button(
                "Load full demo workspace",
                type="primary",
                icon=":material/play_arrow:",
                key="education-load-demo",
            ):
                _activate_demo(root, seed=True)
            return False

        data = _demo_run(lambda: manifest(root)) or {}
        institutions = data.get("institutions", [])
        personas = data.get("personas", [])
        institution_by_id = {item["id"]: item for item in institutions}
        institution_ids = list(institution_by_id)
        selected_institution = str(st.session_state.get("education_institution", ""))
        if selected_institution not in institution_ids and institution_ids:
            selected_institution = institution_ids[0]
        if institution_ids:
            if st.session_state.get("education_demo_institution_picker") not in institution_ids:
                st.session_state.education_demo_institution_picker = selected_institution
            chosen_institution = st.selectbox(
                "Demo institution",
                institution_ids,
                format_func=lambda value: institution_by_id[value]["name"],
                key="education_demo_institution_picker",
            )
            available_personas = [item for item in personas if item["institution_id"] == chosen_institution]
            persona_by_id = {item["id"]: item for item in available_personas}
            persona_ids = list(persona_by_id)
            if st.session_state.get("education_demo_persona_picker") not in persona_ids and persona_ids:
                st.session_state.education_demo_persona_picker = persona_ids[0]
            if persona_ids:
                chosen_persona = st.selectbox(
                    "Demo persona",
                    persona_ids,
                    format_func=lambda value: persona_by_id[value]["switch_label"],
                    key="education_demo_persona_picker",
                )
                st.session_state.education_actor = chosen_persona
                st.session_state.education_institution = chosen_institution

        with st.container(horizontal=True):
            if st.button("Reload demo data", icon=":material/refresh:", key="education-reload-demo"):
                if _demo_run(lambda: seed_demo(root)):
                    _platform.cache_clear()
                    st.toast("Deterministic demo data reloaded.", icon=":material/check_circle:")
                    st.rerun()
            if st.button("View demo manifest", icon=":material/description:", key="education-view-demo-manifest"):
                st.session_state.education_show_demo_manifest = not bool(
                    st.session_state.get("education_show_demo_manifest", False)
                )
            if st.button("Exit demo mode", icon=":material/logout:", key="education-exit-demo"):
                _exit_demo()

        if st.session_state.get("education_show_demo_manifest", False):
            st.json(data, expanded=False)

        confirm = st.checkbox(
            "I understand reset removes only the isolated synthetic Education demo database.",
            key="education-confirm-demo-reset",
        )
        if st.button(
            "Reset demo workspace",
            icon=":material/delete_sweep:",
            disabled=not confirm,
            key="education-reset-demo",
        ):
            result = _demo_run(lambda: reset_demo(root))
            if result:
                st.session_state.education_demo_mode = False
                st.session_state.education_actor = "local-operator"
                st.session_state.education_institution = ""
                _platform.cache_clear()
                st.success("The isolated synthetic demo workspace was reset.", icon=":material/check_circle:")
                st.rerun()
    return True


def _identity_input(label: str, demo_mode: bool) -> None:
    if st.session_state.get("education_presentation_mode", False):
        st.caption("Read-only fictional presentation persona active.")
    elif demo_mode:
        st.caption(f"Active fictional demo identity: {_actor()}")
    elif st.session_state.get("education_authenticated", False):
        actor = _actor()
        with st.container(border=True):
            left, right = st.columns([3, 1], vertical_alignment="center")
            left.markdown(f"**Signed in:** `{actor}`")
            left.caption("Identity is provided by the revocable Education Desktop session.")
            if right.button("Sign out", icon=":material/logout:", key=f"education-session-signout-{actor}"):
                st.session_state.pop("education_phase7_token", None)
                st.session_state.pop("education_authenticated", None)
                st.session_state.education_actor = "local-operator"
                st.session_state.education_institution = ""
                st.rerun()
    else:
        st.text_input(
            label,
            key="education_actor",
            help="Local evaluation identity. Use Education Desktop for secured local sessions.",
        )
        st.caption("For normal desktop use, open Education Desktop and sign in instead of typing an actor ID.")


def _institution(platform: EducationPlatform) -> str:
    actor = _actor()
    institution_id = _safe_identifier(st.session_state.get("education_institution", ""), "")
    options = platform._all(
        """SELECT DISTINCT i.id,i.name,i.kind FROM institutions i
        JOIN memberships m ON m.institution_id=i.id
        WHERE m.user_id=? AND m.state='active' AND i.state='active' ORDER BY i.name""",
        (actor,),
    )
    if options:
        identifiers = [item["id"] for item in options]
        if institution_id not in identifiers:
            institution_id = identifiers[0]
        if st.session_state.get("education_institution_picker") not in identifiers:
            st.session_state.education_institution_picker = institution_id
        selected = st.selectbox(
            "Institution workspace",
            identifiers,
            format_func=lambda value: next(item["name"] for item in options if item["id"] == value),
            key="education_institution_picker",
        )
        st.session_state.education_institution = selected
        institution = next(item for item in options if item["id"] == selected)
        roles = [item["role"] for item in platform.membership(actor, selected)]
        st.caption(
            f"{institution['kind'].title()} · "
            + " · ".join(role.replace("_", " ").title() for role in roles)
        )
    else:
        st.info("Create your first institution workspace to begin.", icon=":material/domain_add:")
        with st.form("institution-create"):
            name = st.text_input("Institution name")
            kind = st.selectbox("Institution type", ["school", "college", "university"])
            if st.form_submit_button(
                "Create institution", type="primary", icon=":material/add_business:"
            ) and name:
                created = _run(lambda: platform.create_institution(actor, name, kind))
                if created:
                    st.session_state.education_institution = created["id"]
                    st.rerun()
    return _safe_identifier(st.session_state.get("education_institution", ""), "")


def _page_platform(root: Path, demo_mode: bool) -> EducationPlatform:
    return _platform(str(root), True) if demo_mode else _platform(str(root))


def _production_only_context(platform: EducationPlatform, page_key: str) -> bool:
    """Force selected workspaces onto institution-backed production storage."""
    demo_active = bool(
        st.session_state.get("education_demo_mode", False)
        or st.session_state.get("education_presentation_mode", False)
    )
    if demo_active and not st.session_state.get("education_authenticated", False):
        st.session_state.education_actor = "local-operator"
        st.session_state.education_institution = ""
    st.session_state.education_demo_mode = False
    st.session_state.education_presentation_mode = False
    for key in (
        "education_demo_institution_picker",
        "education_demo_persona_picker",
        "education_show_demo_manifest",
        "education_confirm_demo_reset",
    ):
        st.session_state.pop(key, None)
    healthy = bool(platform.db.quick_check())
    # Academy keeps the production-only safety boundary but omits this shared
    # context banner so the Lecture Studio opens directly into its controls.
    if page_key != "academy":
        with st.container(border=True):
            left, right = st.columns([3, 1], vertical_alignment="center")
            left.subheader(":material/database: Live institutional workspace")
            left.caption(
                "Every visible record and action is read from or committed to the persistent "
                "Education database. No synthetic seed or demonstration fallback is used."
            )
            if healthy:
                right.badge("LIVE DATABASE", icon=":material/verified:", color="green")
            else:
                right.badge("DATABASE ERROR", icon=":material/error:", color="red")
            st.caption(f"Production context: {page_key} | Database: {platform.db.path.name}")
    if not healthy:
        st.error(
            "The Education database failed its integrity check. Repair the installation before writing records.",
            icon=":material/error:",
        )
    return healthy


def render_education_home(root: Path) -> None:
    _header(
        "BioIntel Education Home",
        "One role-aware home for classes, learning, examinations, scientific updates and institutional governance.",
        "home",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Education user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    with st.container(horizontal=True):
        st.page_link(
            "pages/346_BioIntel_Education_Enterprise.py",
            label="Institution & enterprise platform",
            icon=":material/domain:",
        )
        st.page_link(
            "pages/347_BioIntel_Virtual_Science_Lab.py",
            label="Virtual Science Laboratory",
            icon=":material/science:",
        )
    from .home_ui import render_education_home_workspace

    render_education_home_workspace(platform, actor, institution_id, _run)

def render_classroom(root: Path) -> None:
    _header(
        "BioIntel Classroom",
        "A focused, role-aware workspace for teaching, attendance, assignments, circulars and academic operations.",
        "classroom",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Classroom user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    from .classroom_ui import render_classroom_workspace
    from .phase2 import EducationPhase2
    from .phase2_ui import render_classroom_visuals

    view = st.segmented_control("Classroom experience", ["Visual intelligence", "Operations"], default="Visual intelligence", key=f"education_classroom_experience_{actor}_{institution_id}")
    if view == "Visual intelligence":
        render_classroom_visuals(EducationPhase2(platform), actor, institution_id, _run)
    else:
        render_classroom_workspace(platform, actor, institution_id, _run)


def render_pulse(root: Path) -> None:
    demo_mode = False
    platform = _page_platform(root, demo_mode)
    actor = "local-user"
    institution_id = "local"
    from biointel.science_pulse.ui import render_science_pulse

    render_science_pulse(
        root,
        user_id=actor,
        tenant_id=institution_id,
        can_administer=True,
    )


def render_academy(root: Path) -> None:
    _header(
        "BioIntel Academy",
        "Rights-aware lectures, durable learning progress, assessments, credentials and qualified live-class handoff.",
        "academy",
    )
    platform = _platform(str(root))
    if not _production_only_context(platform, "academy"):
        return
    _identity_input("Academy user ID", False)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    from .academy_ui import render_academy_workspace
    from .phase2 import EducationPhase2
    from .phase2_ui import render_academy_visuals

    view = st.segmented_control("Academy experience", ["Visual intelligence", "Operations"], default="Visual intelligence", key=f"education_academy_experience_{actor}_{institution_id}")
    if view == "Visual intelligence":
        render_academy_visuals(EducationPhase2(platform), actor, institution_id, _run)
    else:
        render_academy_workspace(platform, actor, institution_id, _run, root=root)


def render_universe(root: Path) -> None:
    _header(
        "BioIntel Education Universe",
        "A professional, role-aware hub for twenty tenant-safe education workflows.",
        "universe",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    universe = EducationUniverse(platform)
    _identity_input("Education Universe user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    from .universe_ui import render_universe_workspace

    render_universe_workspace(universe, actor, institution_id, _run)

def render_examinations(root: Path) -> None:
    _header(
        "BioIntel Examination Command Center",
        "Secure exam authoring, server-timed attempts, integrity evidence, grading and locked result publication.",
        "examinations",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Examination user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    from .examination_ui import render_examination_workspace

    render_examination_workspace(platform, actor, institution_id, _run)

# Compatibility aliases retain the original R8 entry points while R9 replaces only
# the selected module renderers.
render_education_home_r8 = render_education_home
render_classroom_r8 = render_classroom
render_examinations_r8 = render_examinations


def render_education_home(root: Path) -> None:
    _header(
        "BioIntel Education Hub",
        "Role-aware institution operations, learning, examinations, services and provenance.",
        "home",
    )
    platform = _platform(str(root))
    if not _production_only_context(platform, "education-home"):
        return
    _identity_input("Education user ID", False)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    with st.container(horizontal=True):
        st.page_link("pages/346_BioIntel_Education_Enterprise.py", label="Institution & enterprise platform", icon=":material/domain:")
        st.page_link("pages/347_BioIntel_Virtual_Science_Lab.py", label="Virtual Science Laboratory", icon=":material/science:")
    from .selective_mega_ui import render_education_hub_mega

    render_education_hub_mega(platform, actor, institution_id, root, _run)


def render_classroom(root: Path) -> None:
    _header(
        "BioIntel Classroom",
        "Persistent classes, stream, classwork, attendance, submissions and academic operations.",
        "classroom",
    )
    platform = _platform(str(root))
    if not _production_only_context(platform, "classroom"):
        return
    _identity_input("Classroom user ID", False)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    from .selective_mega_ui import render_classroom_mega

    render_classroom_mega(platform, actor, institution_id, root, _run)


def render_examinations(root: Path) -> None:
    _header(
        "BioIntel Examination Command Center",
        "Secure delivery, registration, question bank, scheduling, evaluation and versioned results.",
        "examinations",
    )
    platform = _platform(str(root))
    if not _production_only_context(platform, "examinations"):
        return
    _identity_input("Examination user ID", False)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    from .selective_mega_ui import render_examination_mega

    render_examination_mega(platform, actor, institution_id, root, _run)

# Compatibility names now resolve to the production-only selected workspaces.
render_education_home_r8 = render_education_home
render_classroom_r8 = render_classroom
render_examinations_r8 = render_examinations

