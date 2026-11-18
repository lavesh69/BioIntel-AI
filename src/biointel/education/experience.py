from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from ._streamlit_compat import st
from .phase6_visuals import PHASE6_CSS
from biointel.ui.product_experience_v8 import render_product_hero
from biointel.ui.frontend_v10 import capability_grid, kpi_grid, section_header

EDUCATION_PAGES: tuple[tuple[str, str, str, str], ...] = (
    ("home", "pages/339_BioIntel_Education_Home.py", "Education Home", ":material/dashboard:"),
    ("classroom", "pages/340_BioIntel_Classroom.py", "Classroom", ":material/school:"),
    ("suite", "pages/356_BioIntel_Education_Suite.py", "Education Suite", ":material/auto_stories:"),
    ("pulse", "pages/341_BioIntel_Science_Pulse.py", "Science Pulse", ":material/biotech:"),
    ("academy", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "Academy", ":material/video_library:"),
    ("universe", "pages/343_BioIntel_Education_Universe.py", "Universe", ":material/hub:"),
    ("examinations", "pages/344_BioIntel_Examination_Command_Center.py", "Examinations", ":material/assignment_turned_in:"),
    ("intelligence", "pages/345_BioIntel_Education_Intelligence_Hub.py", "Intelligence Hub", ":material/psychology:"),
    ("institution", "pages/346_BioIntel_Institution_Platform_Center.py", "Institution Center", ":material/domain:"),
    ("visuals", "pages/347_BioIntel_Education_Visual_Command_Center.py", "Visual Command", ":material/space_dashboard:"),
    ("desktop", "pages/348_BioIntel_Education_Desktop.py", "Education Desktop", ":material/desktop_windows:"),
    ("mega", "pages/349_BioIntel_Mega_Production_and_Academic_Center.py", "Mega Center", ":material/rocket_launch:"),
    ("completion", "pages/350_BioIntel_Final_Completion_and_Qualification_Center.py", "Final Completion", ":material/verified:"),
    ("autonomy", "pages/351_BioIntel_Local_Autonomy_and_Operations_Center.py", "Local Autonomy", ":material/hub:"),
    ("quality", "pages/352_BioIntel_Academic_Quality_and_Intelligence_Center.py", "Academic Quality", ":material/analytics:"),
    ("runtime", "pages/353_BioIntel_Production_Runtime_and_Research_Intelligence_Center.py", "Runtime & Research", ":material/hub:"),
    ("completion16", "pages/354_BioIntel_Final_Runtime_Evidence_and_Scientific_Workbench_Center.py", "Final Runtime & Science", ":material/biotech:"),
)

PAGE_PERMISSIONS: dict[str, str] = {
    "home": "education.dashboard.view",
    "classroom": "classroom.view",
    "suite": "classroom.view",
    "pulse": "pulse.view",
    "academy": "academy.view",
    "universe": "universe.view",
    "examinations": "exam.view",
    "intelligence": "learning.view",
    "institution": "institution.manage",
    "visuals": "education.dashboard.view",
    "desktop": "education.dashboard.view",
    "mega": "institution.manage",
    "completion": "institution.manage",
    "autonomy": "institution.manage",
    "quality": "education.dashboard.view",
    "runtime": "education.dashboard.view",
    "completion16": "education.dashboard.view",
}

ROLE_LABELS = {
    "platform_administrator": "Platform Admin",
    "institution_administrator": "Institution Admin",
    "principal": "Principal",
    "dean": "Dean",
    "registrar": "Registrar",
    "department_head": "Department Head",
    "examination_controller": "Exam Controller",
    "subject_teacher": "Subject Teacher",
    "class_teacher": "Class Teacher",
    "lecturer": "Lecturer",
    "assistant_professor": "Assistant Professor",
    "professor": "Professor",
    "teaching_assistant": "Teaching Assistant",
    "laboratory_instructor": "Lab Instructor",
    "academic_mentor": "Academic Mentor",
    "class_coordinator": "Class Coordinator",
    "school_student": "School Student",
    "college_student": "College Student",
    "university_student": "University Student",
    "parent_guardian": "Guardian",
}

EDUCATION_CSS = r"""
<style>
:root {
  --edu-bg: #07111f;
  --edu-panel: rgba(15, 29, 49, .82);
  --edu-panel-strong: rgba(18, 37, 62, .96);
  --edu-border: rgba(148, 184, 224, .18);
  --edu-text: #eff7ff;
  --edu-muted: #a9bdd4;
  --edu-cyan: #4fe4ff;
  --edu-blue: #6d8cff;
  --edu-green: #55e6a5;
  --edu-warning: #ffcb6b;
  --edu-shadow: 0 22px 60px rgba(0, 0, 0, .28);
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 8% -5%, rgba(79, 228, 255, .12), transparent 30rem),
    radial-gradient(circle at 88% 5%, rgba(109, 140, 255, .14), transparent 32rem),
    linear-gradient(180deg, #07111f 0%, #0a1423 48%, #08111d 100%);
}
[data-testid="stMainBlockContainer"] {max-width: 1500px; padding-top: 1.2rem; padding-bottom: 6rem;}
[data-testid="stSidebar"] {background: linear-gradient(180deg, rgba(7,17,31,.98), rgba(11,25,43,.98)); border-right: 1px solid var(--edu-border);}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] span {font-size: .91rem;}
.edu-app-hero {
  position: relative; overflow: hidden; padding: 1.45rem 1.55rem; margin: .2rem 0 1rem;
  border: 1px solid var(--edu-border); border-radius: 24px;
  background: linear-gradient(135deg, rgba(18,37,62,.96), rgba(10,25,44,.9));
  box-shadow: var(--edu-shadow);
}
.edu-app-hero:after {content:""; position:absolute; inset:auto -5rem -8rem auto; width:18rem; height:18rem; border-radius:50%; background:radial-gradient(circle, rgba(79,228,255,.22), transparent 68%);}
.edu-eyebrow {font-size:.72rem; letter-spacing:.16em; font-weight:800; text-transform:uppercase; color:var(--edu-cyan); margin-bottom:.45rem;}
.edu-app-hero h1 {color:var(--edu-text); font-size:clamp(1.65rem, 3vw, 2.55rem); line-height:1.08; margin:0 0 .55rem;}
.edu-app-hero p {color:var(--edu-muted); font-size:1rem; max-width:72rem; margin:0;}
.edu-trust-row {display:flex; flex-wrap:wrap; gap:.45rem; margin-top:1rem;}
.edu-trust-pill {display:inline-flex; align-items:center; gap:.35rem; padding:.36rem .65rem; border-radius:999px; border:1px solid var(--edu-border); background:rgba(255,255,255,.045); color:#dbeaff; font-size:.78rem; font-weight:650;}
.edu-context {display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; padding:.78rem 1rem; margin:.15rem 0 .9rem; border:1px solid var(--edu-border); border-radius:16px; background:rgba(12,27,47,.86); backdrop-filter:blur(14px);}
.edu-context-main {display:flex; gap:.7rem; align-items:center; flex-wrap:wrap; color:var(--edu-text);}
.edu-avatar {display:grid; place-items:center; width:2.3rem; height:2.3rem; border-radius:12px; background:linear-gradient(135deg,var(--edu-cyan),var(--edu-blue)); color:#06111f; font-weight:900;}
.edu-context small {display:block; color:var(--edu-muted);}
.edu-role {padding:.3rem .55rem; border-radius:999px; background:rgba(85,230,165,.11); border:1px solid rgba(85,230,165,.28); color:#a9ffd4; font-size:.74rem; font-weight:750;}
.edu-section-title {font-weight:800; color:var(--edu-text); margin:.8rem 0 .35rem;}
.edu-card-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.75rem; margin:.7rem 0 1rem;}
.edu-stat-card {padding:1rem; border-radius:18px; border:1px solid var(--edu-border); background:linear-gradient(145deg,rgba(20,39,65,.9),rgba(11,26,45,.86)); box-shadow:0 12px 32px rgba(0,0,0,.18);}
.edu-stat-card .label {font-size:.78rem; color:var(--edu-muted); margin-bottom:.35rem;}
.edu-stat-card .value {font-size:1.45rem; font-weight:850; color:var(--edu-text);}
.edu-stat-card .detail {font-size:.72rem; color:#8ca7c4; margin-top:.3rem;}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:var(--edu-border)!important; border-radius:18px!important; background:rgba(13,28,48,.72);}
[data-testid="stMetric"] {padding:.3rem .1rem;}
[data-testid="stMetricValue"] {color:var(--edu-text); font-weight:800;}
.stButton > button, .stDownloadButton > button, [data-testid="stPageLink"] a {border-radius:12px!important; min-height:2.65rem; font-weight:700;}
.stButton > button[kind="primary"] {background:linear-gradient(135deg,#28cde7,#6d8cff); border:0; color:#05111d; box-shadow:0 10px 30px rgba(79,228,255,.2);}
[data-baseweb="tab-list"] {gap:.35rem; padding:.28rem; border:1px solid var(--edu-border); border-radius:14px; background:rgba(10,24,42,.72);}
[data-baseweb="tab"] {border-radius:10px; padding:.55rem .85rem;}
[data-baseweb="tab"][aria-selected="true"] {background:rgba(79,228,255,.12); color:#b9f6ff;}
[data-testid="stDataFrame"] {border:1px solid var(--edu-border); border-radius:16px; overflow:hidden;}
[data-testid="stAlert"] {border-radius:14px;}
[data-testid="stForm"] {border:1px solid var(--edu-border); border-radius:18px; padding:1rem; background:rgba(12,27,47,.62);}
:where(button,a,input,textarea,select,[tabindex]):focus-visible {outline:3px solid var(--edu-cyan)!important; outline-offset:3px!important; box-shadow:0 0 0 4px rgba(79,228,255,.18)!important;}
[data-testid="stTooltipContent"]{max-width:28rem;line-height:1.45}
.edu-app-hero h1,.edu-app-hero p{max-width:78rem}
.edu-nav-caption {font-size:.75rem; color:var(--edu-muted); margin:.15rem 0 .45rem;}
.edu-module-card {position:relative; overflow:hidden; padding:1rem; min-height:9rem; border:1px solid var(--edu-border); border-radius:20px; background:linear-gradient(145deg,rgba(20,39,65,.94),rgba(9,23,40,.9)); box-shadow:0 16px 40px rgba(0,0,0,.2);}
.edu-module-card:after {content:""; position:absolute; width:8rem; height:8rem; border-radius:50%; right:-4rem; bottom:-5rem; background:rgba(79,228,255,.09);}
.edu-module-card h3 {margin:.35rem 0; color:var(--edu-text); font-size:1.05rem;}
.edu-module-card p {color:var(--edu-muted); font-size:.82rem; line-height:1.45;}
.edu-kicker {font-size:.68rem; text-transform:uppercase; letter-spacing:.14em; color:var(--edu-cyan); font-weight:800;}
.edu-progress-track {height:.55rem; border-radius:999px; background:rgba(255,255,255,.08); overflow:hidden; margin:.55rem 0;}
.edu-progress-fill {height:100%; border-radius:999px; background:linear-gradient(90deg,var(--edu-cyan),var(--edu-blue));}
.edu-notice {display:flex; gap:.75rem; align-items:flex-start; padding:.85rem 1rem; margin:.5rem 0; border:1px solid var(--edu-border); border-radius:16px; background:rgba(15,32,54,.78);}
.edu-notice strong {color:var(--edu-text);}.edu-notice small {display:block;color:var(--edu-muted);margin-top:.2rem;}
.edu-chip {display:inline-flex; padding:.26rem .52rem; border-radius:999px; border:1px solid var(--edu-border); color:#d8eaff; font-size:.7rem; font-weight:700; background:rgba(255,255,255,.04);}
.edu-split-grid {display:grid; grid-template-columns:minmax(0,1.35fr) minmax(18rem,.65fr); gap:1rem; align-items:start;}

.edu-platform-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem;margin:.8rem 0 1rem;}
.edu-readiness-bar {height:.72rem;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;}
.edu-readiness-bar > span {display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--edu-green),var(--edu-cyan),var(--edu-blue));}
.edu-control-band {display:flex;gap:.55rem;flex-wrap:wrap;padding:.75rem;border:1px solid var(--edu-border);border-radius:16px;background:rgba(12,27,47,.68);}
@media (max-width: 1050px) {.edu-platform-grid {grid-template-columns:1fr 1fr;}}
@media (max-width: 700px) {.edu-platform-grid {grid-template-columns:1fr;}}
@media (max-width: 900px) {.edu-split-grid {grid-template-columns:1fr;}}
@media (max-width: 1050px) {.edu-card-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
@media (max-width: 700px) {
  [data-testid="stMainBlockContainer"] {padding-left:.8rem; padding-right:.8rem; padding-top:.7rem;}
  .edu-app-hero {padding:1.1rem; border-radius:18px;}
  .edu-card-grid {grid-template-columns:1fr 1fr; gap:.55rem;}
  .edu-stat-card {padding:.8rem; border-radius:14px;}
  .edu-stat-card .value {font-size:1.2rem;}
  .edu-context {padding:.7rem; border-radius:14px;}
}
</style>
"""


def apply_education_design() -> None:
    if not st.session_state.get("_education_design_v6_loaded"):
        st.markdown(EDUCATION_CSS + PHASE6_CSS, unsafe_allow_html=True)
        st.session_state._education_design_v6_loaded = True
    scale = float(st.session_state.get("education_font_scale", 1.0) or 1.0)
    density = str(st.session_state.get("education_density", "comfortable"))
    theme = str(st.session_state.get("education_theme", "dark"))
    high = bool(st.session_state.get("education_high_contrast", False))
    reduced = bool(st.session_state.get("education_reduced_motion", False))
    dyslexia = bool(st.session_state.get("education_dyslexia_mode", False))
    overrides = [f"--edu-font-scale:{max(.85,min(1.5,scale))};"]
    if theme == "light":
        overrides.extend(["--edu-bg:#eef5fb;", "--edu-panel:rgba(255,255,255,.9);", "--edu-panel-strong:#fff;", "--edu-border:rgba(38,75,108,.22);", "--edu-text:#102235;", "--edu-muted:#526a80;"])
    if high:
        overrides.extend(["--edu-border:rgba(255,255,255,.7);", "--edu-text:#fff;", "--edu-muted:#eef5ff;"])
    dynamic = f"<style>[data-testid='stAppViewContainer']{{{''.join(overrides)}}}"
    if density == "compact":
        dynamic += "[data-testid='stMainBlockContainer']{padding-top:.45rem}.edu-stat-card,.edu6-metric{padding:.62rem}[data-testid='stForm']{padding:.65rem}"
    if reduced:
        dynamic += "*{animation:none!important;transition:none!important;scroll-behavior:auto!important}"
    if dyslexia:
        dynamic += "body,[data-testid='stAppViewContainer']{font-family:Verdana,Tahoma,Arial,sans-serif!important;letter-spacing:.018em;word-spacing:.04em}"
    dynamic += "</style>"
    st.markdown(dynamic, unsafe_allow_html=True)


def render_accessibility_toolbar() -> None:
    with st.expander(":material/accessibility_new: Appearance & accessibility", expanded=False):
        columns = st.columns(3)
        with columns[0]:
            st.selectbox("Theme", ["dark", "light", "system"], key="education_theme")
            st.selectbox("Density", ["comfortable", "compact"], key="education_density")
        with columns[1]:
            st.slider("Font scale", .85, 1.5, 1.0, .05, key="education_font_scale")
            st.toggle("High contrast", key="education_high_contrast")
        with columns[2]:
            st.toggle("Reduced motion", key="education_reduced_motion")
            st.toggle("Dyslexia-friendly text", key="education_dyslexia_mode")
        st.caption("Keyboard focus, text scaling, contrast and reduced-motion preferences apply across Education OS pages.")


def render_app_header(page_key: str, title: str, subtitle: str, *, eyebrow: str = "BIOINTEL EDUCATION OS") -> None:
    apply_education_design()
    render_product_hero(
        page_key,
        title,
        subtitle,
        eyebrow=eyebrow,
        chips=(
            "Local-first institutional data",
            "Permission-aware workspace",
            "Audit and evidence trail",
            "Desktop scientific experience",
        ),
    )
    # Every Education OS module now receives a visible, icon-led capability deck.
    # This is presentation-only and does not alter permission or workflow logic.
    capability_grid(page_key)
    st.session_state.education_active_page = page_key
    render_accessibility_toolbar()


def render_app_navigation(active_key: str, platform: Any | None = None, actor: str = "", institution_id: str = "") -> None:
    visible = list(EDUCATION_PAGES)
    if platform is not None and actor and institution_id:
        try:
            from .permissions import PermissionService
            resolver = PermissionService(platform)
            visible = [page for page in EDUCATION_PAGES if resolver.has(actor, institution_id, PAGE_PERMISSIONS.get(page[0], "education.dashboard.view"))]
        except Exception:
            visible = list(EDUCATION_PAGES)
    st.markdown('<div class="edu-nav-caption">Education applications · role-aware navigation</div>', unsafe_allow_html=True)
    for offset in range(0, len(visible), 4):
        page_row = visible[offset:offset + 4]
        columns = st.columns(len(page_row), gap="small")
        for column, (key, path, label, icon) in zip(columns, page_row):
            with column:
                try:
                    st.page_link(path, label=("● " if key == active_key else "") + label, icon=icon, width="stretch")
                except (KeyError, RuntimeError, TypeError):
                    st.caption(("Active · " if key == active_key else "") + label)


def _primary_role(roles: set[str]) -> str:
    priority = (
        "platform_administrator", "institution_administrator", "principal", "dean",
        "registrar", "department_head", "examination_controller", "professor",
        "assistant_professor", "lecturer", "subject_teacher", "class_teacher",
        "laboratory_instructor", "teaching_assistant", "academic_mentor",
        "university_student", "college_student", "school_student", "parent_guardian",
    )
    return next((role for role in priority if role in roles), sorted(roles)[0] if roles else "member")


def render_workspace_context(platform: Any, actor: str, institution_id: str) -> set[str]:
    memberships = platform.membership(actor, institution_id)
    roles = {str(row["role"]) for row in memberships}
    institution = platform._one("SELECT name,kind FROM institutions WHERE id=?", (institution_id,)) or {}
    primary = _primary_role(roles)
    actor_text = str(actor)
    friendly_actor = actor_text.replace("_", " ").replace("-", " ").strip().title() or "BioIntel Member"
    initials = "".join(part[:1].upper() for part in friendly_actor.split()[:2]) or "BI"
    role_html = "".join(f'<span class="edu-role">{html.escape(ROLE_LABELS.get(role, role.replace("_", " ").title()))}</span>' for role in sorted(roles)[:4])
    st.markdown(
        f"""
        <div class="edu-context">
          <div class="edu-context-main">
            <div class="edu-avatar">{html.escape(initials[:2])}</div>
            <div><strong>{html.escape(friendly_actor)}</strong><small>{html.escape(str(institution.get('name') or 'Institution'))} · {html.escape(str(institution.get('kind') or 'workspace').title())} · ID {html.escape(actor_text[-12:])}</small></div>
          </div>
          <div>{role_html or '<span class="edu-role">Member</span>'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.session_state.education_primary_role = primary
    active_key = str(st.session_state.get("education_active_page", "home"))
    render_app_navigation(active_key, platform, actor, institution_id)
    try:
        from .phase6 import EducationPhase6Service
        phase6 = EducationPhase6Service(platform)
        preferences = phase6.preferences(actor, institution_id)
        st.session_state.setdefault("education_theme", preferences.get("theme", "dark"))
        st.session_state.setdefault("education_density", preferences.get("density", "comfortable"))
        st.session_state.setdefault("education_font_scale", float(preferences.get("font_scale", 1.0) or 1.0))
        st.session_state.setdefault("education_high_contrast", bool(preferences.get("high_contrast", 0)))
        st.session_state.setdefault("education_reduced_motion", bool(preferences.get("reduced_motion", 0)))
        st.session_state.setdefault("education_dyslexia_mode", bool(preferences.get("dyslexia_mode", 0)))
        phase6.record_visit(actor, institution_id, active_key)
    except Exception:
        pass
    return roles


def render_role_snapshot(platform: Any, actor: str, institution_id: str) -> None:
    data = platform.dashboard(actor, institution_id)
    roles = set(data.get("roles", []))
    cards: list[tuple[str, Any, str]] = []
    if roles & {"school_student", "college_student", "university_student"}:
        cards.extend([
            ("Pending assignments", data.get("pending_assignments", 0), "Items awaiting submission"),
            ("Attendance records", data.get("attendance_records", 0), "Visible recorded sessions"),
        ])
        upcoming = platform._one(
            """SELECT COUNT(*) n FROM examinations e JOIN enrollments x ON x.subject_id=e.subject_id
            WHERE x.student_id=? AND e.institution_id=? AND e.state='published' AND e.ends_at>=?""",
            (actor, institution_id, datetime.now(timezone.utc).isoformat()),
        ) or {"n": 0}
        cards.append(("Upcoming exams", int(upcoming["n"]), "Published examination windows"))
        progress = platform._one(
            """SELECT COUNT(*) n FROM academy_enrollments WHERE institution_id=? AND student_id=? AND state='active'""",
            (institution_id, actor),
        ) or {"n": 0}
        cards.append(("Active courses", int(progress["n"]), "Academy enrollments"))
    elif roles & {"parent_guardian"}:
        linked = platform._one("SELECT COUNT(*) n FROM guardian_links WHERE institution_id=? AND guardian_id=? AND state='active'", (institution_id, actor)) or {"n": 0}
        cards = [
            ("Linked learners", int(linked["n"]), "Consent-approved profiles"),
            ("Privacy mode", "Active", "Student-controlled access"),
            ("Circular access", "Audience-based", "Only addressed notices"),
            ("Data source", "Institution", "No inferred grades"),
        ]
    else:
        cards.extend([
            ("Assigned subjects", data.get("assigned_subjects", 0), "Active teaching responsibilities"),
            ("Pending grading", data.get("pending_grading", 0), "Submitted work awaiting grade"),
            ("Students", data.get("students", "—"), "Institution membership"),
            ("Faculty", data.get("faculty", "—"), "Active academic staff"),
        ])
    cards = (cards + [("Workspace", "Ready", "Role-aware education services")])[:4]
    icon_map = {
        "Pending assignments": "▤", "Attendance records": "✓", "Upcoming exams": "◉", "Active courses": "▷",
        "Linked learners": "◎", "Privacy mode": "◇", "Circular access": "↗", "Data source": "▣",
        "Assigned subjects": "▦", "Pending grading": "▥", "Students": "◫", "Faculty": "◆", "Workspace": "⌘",
    }
    kpi_grid((icon_map.get(str(label), "◆"), str(label), value, str(detail)) for label, value, detail in cards)
