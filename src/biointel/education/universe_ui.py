from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from ._streamlit_compat import st

from .universe import EducationUniverse, MODULES, ModuleDefinition, TRANSITIONS
from biointel.ui.frontend_v10 import empty_state

Run = Callable[[Callable[[], Any]], Any]

CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Personalized learning", ("adaptive_learning", "shiro_tutor", "learning_analytics", "gamified_learning")),
    ("Academic operations", ("academic_erp", "question_bank", "quality_support", "offline_learning")),
    ("Scientific learning", ("virtual_science_lab", "bioinformatics_sandbox", "laboratory_management", "lecture_intelligence")),
    ("Research and knowledge", ("digital_library", "research_hub", "open_science")),
    ("Student growth", ("career_hub", "competition_hub", "academic_portfolio")),
    ("Collaboration and safety", ("collaboration_network", "safety_moderation")),
)
CATEGORY_BY_MODULE = {
    key: category for category, keys in CATEGORIES for key in keys
}
MODULE_ICONS: Mapping[str, str] = {
    "adaptive_learning": ":material/route:",
    "virtual_science_lab": ":material/science:",
    "bioinformatics_sandbox": ":material/data_object:",
    "shiro_tutor": ":material/smart_toy:",
    "academic_erp": ":material/account_balance:",
    "digital_library": ":material/local_library:",
    "research_hub": ":material/biotech:",
    "competition_hub": ":material/emoji_events:",
    "career_hub": ":material/work:",
    "academic_portfolio": ":material/workspace_premium:",
    "laboratory_management": ":material/lab_panel:",
    "question_bank": ":material/quiz:",
    "lecture_intelligence": ":material/subtitles:",
    "learning_analytics": ":material/monitoring:",
    "collaboration_network": ":material/hub:",
    "open_science": ":material/public:",
    "offline_learning": ":material/offline_bolt:",
    "safety_moderation": ":material/health_and_safety:",
    "quality_support": ":material/fact_check:",
    "gamified_learning": ":material/military_tech:",
}
RECOMMENDATIONS: Mapping[str, tuple[str, ...]] = {
    "student": ("adaptive_learning", "shiro_tutor", "research_hub", "career_hub", "academic_portfolio", "gamified_learning"),
    "teacher": ("question_bank", "learning_analytics", "lecture_intelligence", "virtual_science_lab", "digital_library", "research_hub"),
    "administrator": ("academic_erp", "quality_support", "collaboration_network", "safety_moderation", "offline_learning", "learning_analytics"),
}
PENDING_STATES = {"submitted", "under_review", "open"}
DEMO_SOURCE_STATUSES = {"demo", "demo_seed", "seeded_demo", "synthetic_demo"}


@dataclass(frozen=True)
class FieldSpec:
    label: str
    kind: str = "text"
    help: str = ""
    placeholder: str = ""
    options: tuple[str, ...] = ()
    default: Any = ""


FIELD_SPECS: Mapping[str, FieldSpec] = {
    "evidence": FieldSpec("Evidence", "long", "Describe real, reviewable evidence.", "Evidence source, observation, result, or artifact reference"),
    "rationale": FieldSpec("Rationale", "long", "Explain why this action or recommendation is appropriate."),
    "expected_outcome": FieldSpec("Expected outcome", "long", "State an observable learning outcome without diagnostic labelling."),
    "dismissible": FieldSpec("Learner can dismiss this recommendation", "boolean", "Required for adjustable adaptive learning.", default=True),
    "objective": FieldSpec("Learning objective", "long"),
    "safety_briefing": FieldSpec("Simulation safety briefing", "long", "Explain the virtual-only safety boundary."),
    "simulation_only": FieldSpec("This record is for simulation only", "boolean", "Virtual lab records cannot authorize physical experiments.", default=True),
    "dataset_label": FieldSpec("Dataset label", help="Identify the permitted educational dataset."),
    "method": FieldSpec("Method", "long", "Describe the educational or reproducibility method."),
    "parameters": FieldSpec("Parameters", "long", "Describe bounded parameters in plain language; shell commands are not accepted."),
    "resource_limit_seconds": FieldSpec("Resource limit (seconds)", "integer", "The sandbox accepts 1–3,600 seconds.", default=300),
    "request": FieldSpec("Learning request", "long", "Do not include protected answers or sensitive student data."),
    "ai_generated": FieldSpec("Label this content as AI-generated", "boolean", "Shiro drafts require visible AI labelling and human review.", default=True),
    "review_status": FieldSpec("Review status", "select", options=("Draft — not reviewed", "Human review pending", "Human reviewed")),
    "subject_user_id": FieldSpec("Student or member user ID", help="Use the institution-controlled identifier."),
    "academic_session": FieldSpec("Academic session", placeholder="For example, 2026–27"),
    "source_url": FieldSpec("Source URL", "url", "A legitimate HTTP(S) source is required.", "https://"),
    "license_or_access": FieldSpec("Licence or access basis", "long", "Record the licence, subscription, permission, or open-access basis."),
    "academic_level": FieldSpec("Academic level", "select", options=("School", "Undergraduate", "Postgraduate", "Professional")),
    "research_question": FieldSpec("Research question", "long"),
    "ethics_consideration": FieldSpec("Ethics consideration", "long", "Record applicable ethics, consent, privacy, or safety considerations."),
    "rules": FieldSpec("Rules and evaluation basis", "long"),
    "deadline": FieldSpec("Deadline", placeholder="YYYY-MM-DD and timezone"),
    "eligibility": FieldSpec("Eligibility", "long"),
    "responsible_staff": FieldSpec("Responsible staff member"),
    "subject": FieldSpec("Subject"),
    "learning_outcome": FieldSpec("Learning outcome", "long"),
    "lecture_id": FieldSpec("Lecture ID"),
    "processing_status": FieldSpec("Processing status", "select", options=("Not started", "Dependency required", "Queued", "Processing", "Output ready for review")),
    "metric_definition": FieldSpec("Metric definition", "long", "Explain exactly what is counted and how it is derived."),
    "date_range": FieldSpec("Date range", help="Use a bounded, reproducible period.", placeholder="YYYY-MM-DD to YYYY-MM-DD"),
    "source_events": FieldSpec("Source events", "long", "List the persisted education events used by the metric."),
    "partner_institution_id": FieldSpec("Partner institution ID"),
    "terms": FieldSpec("Collaboration terms", "long"),
    "provenance": FieldSpec("Provenance", "long", "Record source, version, method, and ownership lineage."),
    "license": FieldSpec("Licence"),
    "device_scope": FieldSpec("Device scope", help="Identify the managed offline boundary."),
    "reason": FieldSpec("Reason for report", "long", "Provide only what authorized review requires."),
    "review_period": FieldSpec("Review period", placeholder="For example, Semester 1, 2026–27"),
}


def _friendly(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _scope(actor: str, institution_id: str) -> str:
    clean = lambda value: "".join(ch if ch.isalnum() else "_" for ch in value)
    return f"education_universe_{clean(actor)}_{clean(institution_id)}"


def _definition(module_key: str) -> ModuleDefinition:
    return next(module for module in MODULES if module.key == module_key)


def _persona(roles: Iterable[str]) -> str:
    roles = set(roles)
    administrators = {"platform_administrator", "institution_administrator", "principal", "dean", "registrar", "department_head", "examination_controller"}
    teachers = {"subject_teacher", "class_teacher", "lecturer", "assistant_professor", "professor", "teaching_assistant", "laboratory_instructor", "academic_mentor", "class_coordinator"}
    if roles & administrators:
        return "administrator"
    if roles & teachers:
        return "teacher"
    return "student"


def _initialise(scope: str) -> None:
    st.session_state.setdefault(f"{scope}_favourites", [])
    st.session_state.setdefault(f"{scope}_recent", [])
    st.session_state.setdefault(f"{scope}_view", "Module hub")
    st.session_state.setdefault(f"{scope}_create_module", MODULES[0].key)


def _open_module(scope: str, module_key: str) -> None:
    recent = [key for key in st.session_state.get(f"{scope}_recent", []) if key != module_key]
    st.session_state[f"{scope}_recent"] = [module_key, *recent][:6]
    st.session_state[f"{scope}_create_module"] = module_key
    st.session_state[f"{scope}_view"] = "Create record"


def _toggle_favourite(scope: str, module_key: str) -> None:
    favourites = list(st.session_state.get(f"{scope}_favourites", []))
    if module_key in favourites:
        favourites.remove(module_key)
    else:
        favourites.append(module_key)
    st.session_state[f"{scope}_favourites"] = favourites


def _switch_view(scope: str, view: str) -> None:
    st.session_state[f"{scope}_view"] = view


def _counts(dashboard: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int], Counter[str]]:
    totals: defaultdict[str, int] = defaultdict(int)
    pending: defaultdict[str, int] = defaultdict(int)
    states: Counter[str] = Counter()
    for row in dashboard.get("stored_counts", []) or []:
        key, state, count = str(row.get("module_key", "")), str(row.get("state", "")), int(row.get("count") or 0)
        totals[key] += count
        states[state] += count
        if state in PENDING_STATES:
            pending[key] += count
    return dict(totals), dict(pending), states


def _demo_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        if str(record.get("source_status", "")).lower() in DEMO_SOURCE_STATUSES:
            counts[str(record.get("module_key", ""))] += 1
    return dict(counts)


def _recommendations(modules: list[Mapping[str, Any]], roles: list[str], totals: Mapping[str, int]) -> list[str]:
    allowed = {str(module["key"]) for module in modules if module.get("can_create")}
    order = list(RECOMMENDATIONS[_persona(roles)])
    rank = {key: index for index, key in enumerate(order)}
    order.sort(key=lambda key: (totals.get(key, 0) > 0, rank[key]))
    return [key for key in order if key in allowed]


def _field_spec(name: str) -> FieldSpec:
    return FIELD_SPECS.get(name, FieldSpec(_friendly(name), help="Required evidence field from the module definition."))


def _render_field(name: str, prefix: str) -> Any:
    spec, key = _field_spec(name), f"{prefix}_{name}"
    if spec.kind == "boolean":
        return st.checkbox(spec.label, value=bool(spec.default), help=spec.help or None, key=key)
    if spec.kind == "integer":
        return int(st.number_input(spec.label, min_value=1, max_value=3600, value=int(spec.default or 300), step=30, help=spec.help or None, key=key))
    if spec.kind == "select":
        return st.selectbox(spec.label, list(spec.options), help=spec.help or None, key=key)
    if spec.kind == "long":
        return st.text_area(spec.label, placeholder=spec.placeholder or None, help=spec.help or None, key=key)
    return st.text_input(spec.label, placeholder=spec.placeholder or None, help=spec.help or None, key=key)


def _quick_workspace_link(path: str, label: str, icon: str) -> None:
    with st.container(border=True, height="stretch"):
        try:
            st.page_link(path, label=label, icon=icon, width="stretch")
        except (KeyError, RuntimeError):
            st.caption(f"{label} — open it from the application sidebar.")


def _command_center(
    universe: EducationUniverse,
    actor: str,
    institution_id: str,
    run: Run,
    dashboard: Mapping[str, Any],
    records: list[Mapping[str, Any]],
    modules: list[Mapping[str, Any]],
    roles: list[str],
) -> None:
    platform = universe.platform
    institution = run(
        lambda: platform._one(
            "SELECT name,kind,timezone FROM institutions WHERE id=? AND state='active'",
            (institution_id,),
        )
    ) or {}
    role_dashboard = run(lambda: platform.dashboard(actor, institution_id)) or {}
    persona = _persona(roles)
    totals, pending, _ = _counts(dashboard)
    demo_count = sum(
        str(record.get("source_status", "")).lower() in DEMO_SOURCE_STATUSES
        for record in records
    )

    with st.container(border=True):
        heading_col, status_col = st.columns([1.35, 1], vertical_alignment="center")
        with heading_col:
            st.subheader(":material/dashboard: Education Command Center")
            st.caption(
                f"{institution.get('name', 'Institution workspace')} · "
                f"{_friendly(str(institution.get('kind', 'institution')))} · "
                f"{_friendly(persona)} view"
            )
        with status_col:
            with st.container(horizontal=True):
                st.badge(_friendly(persona), icon=":material/person:", color="blue")
                st.badge(
                    f"Demo records · {demo_count}",
                    icon=":material/science:",
                    color="green" if demo_count else "gray",
                )

        if persona == "administrator":
            metrics = (
                ("Students", int(role_dashboard.get("students") or 0), "Distinct persisted student memberships"),
                ("Faculty", int(role_dashboard.get("faculty") or 0), "Distinct persisted faculty memberships"),
                ("Pending actions", sum(pending.values()), "Open, submitted, or under-review Universe records"),
                ("Universe records", sum(totals.values()), "Durable, non-deleted institution records"),
            )
        elif persona == "teacher":
            metrics = (
                ("Assigned subjects", int(role_dashboard.get("assigned_subjects") or 0), "Active subject assignments"),
                ("Pending grading", int(role_dashboard.get("pending_grading") or 0), "Submitted work without a stored grade"),
                ("Pending actions", sum(pending.values()), "Open, submitted, or under-review Universe records"),
                ("Accessible records", len(records), "Records visible through the permission boundary"),
            )
        else:
            metrics = (
                ("Pending assignments", int(role_dashboard.get("pending_assignments") or 0), "Published assignments without a submission"),
                ("Attendance records", int(role_dashboard.get("attendance_records") or 0), "Persisted attendance visible to this learner"),
                ("Accessible records", len(records), "Records visible through the permission boundary"),
                ("Available modules", sum(bool(module.get("can_create")) for module in modules), "Modules available for this current role"),
            )
        with st.container(horizontal=True):
            for label, value, help_text in metrics:
                st.metric(label, value, border=True, help=help_text)
        st.caption("These are persisted service counts. Zero is a valid empty state, not synthetic demo data.")

    with st.expander("Quick education workspaces", icon=":material/apps:"):
        links = (
            ("pages/340_BioIntel_Classroom.py", "Classroom", ":material/school:"),
            ("pages/342_BioIntel_Academy_and_Lecture_Studio.py", "Academy", ":material/play_lesson:"),
            ("pages/341_BioIntel_Science_Pulse.py", "Science Pulse", ":material/newspaper:"),
            ("pages/273_Shiro_AI.py", "Shiro AI", ":material/smart_toy:"),
            ("pages/300_BioIntel_Connect_Home.py", "BioIntel Connect", ":material/hub:"),
        )
        for offset in range(0, len(links), 3):
            columns = st.columns(3, gap="small")
            for column, (path, label, icon) in zip(columns, links[offset : offset + 3]):
                with column:
                    _quick_workspace_link(path, label, icon)

def _workspace_summary(dashboard: Mapping[str, Any], modules: list[Mapping[str, Any]], records: list[Mapping[str, Any]]) -> None:
    totals, pending, _ = _counts(dashboard)
    demos = _demo_counts(records)
    with st.container(horizontal=True):
        st.metric("Available modules", sum(bool(module.get("can_create")) for module in modules), border=True)
        st.metric("Persisted records", sum(totals.values()), border=True)
        st.metric("Pending actions", sum(pending.values()), border=True)
        st.metric("Demo records", sum(demos.values()), border=True)
    st.caption("Counts come from the durable Education Universe database. Demo counts include only records explicitly labelled with a demo source status.")


def _module_card(module: Mapping[str, Any], scope: str, roles: list[str], totals: Mapping[str, int], pending: Mapping[str, int], demos: Mapping[str, int]) -> None:
    key = str(module["key"])
    available = bool(module.get("can_create"))
    favourites = st.session_state.get(f"{scope}_favourites", [])
    with st.container(border=True, height="stretch"):
        st.subheader(f"{MODULE_ICONS.get(key, ':material/apps:')} {module['name']}")
        with st.container(horizontal=True):
            st.badge(CATEGORY_BY_MODULE[key], color="blue")
            st.badge(
                "Available" if available else "View only",
                icon=":material/check_circle:" if available else ":material/visibility:",
                color="green" if available else "gray",
            )
        st.write(str(module["purpose"]))
        st.caption(f"{totals.get(key, 0)} persisted · {demos.get(key, 0)} demo · {pending.get(key, 0)} pending")
        st.caption("Current role: " + (", ".join(_friendly(role) for role in roles) or "No active role"))
        with st.container(horizontal=True):
            st.button(
                "Open module",
                icon=":material/arrow_forward:",
                type="primary" if available else "secondary",
                key=f"{scope}_open_{key}",
                on_click=_open_module,
                args=(scope, key),
            )
            st.button(
                "Remove favourite" if key in favourites else "Add favourite",
                icon=":material/star:" if key in favourites else ":material/star_border:",
                key=f"{scope}_favourite_{key}",
                on_click=_toggle_favourite,
                args=(scope, key),
            )


def _module_hub(modules: list[Mapping[str, Any]], roles: list[str], dashboard: Mapping[str, Any], records: list[Mapping[str, Any]], scope: str) -> None:
    totals, pending, _ = _counts(dashboard)
    demos = _demo_counts(records)
    favourites = list(st.session_state.get(f"{scope}_favourites", []))
    recent = list(st.session_state.get(f"{scope}_recent", []))
    recommended = _recommendations(modules, roles, totals)

    st.subheader("Explore the Education Universe")
    st.caption("Search by learning need, then open a guided, permission-aware workflow.")
    search_col, category_col = st.columns([1.35, 1])
    with search_col:
        query = st.text_input(
            "Search modules",
            placeholder="Search learning, research, safety, assessment…",
            icon=":material/search:",
            key=f"{scope}_search",
        )
    with category_col:
        category = st.selectbox("Category", ["All categories", *[item[0] for item in CATEGORIES]], key=f"{scope}_category")
    availability_col, collection_col = st.columns([1, 1.35])
    with availability_col:
        availability = st.segmented_control("Availability", ["All", "Available", "View only"], default="All", key=f"{scope}_availability")
    with collection_col:
        collection = st.pills("Collection", ["All modules", "Favourites", "Recent", "Recommended"], default="All modules", key=f"{scope}_collection")

    collections = {"Favourites": favourites, "Recent": recent, "Recommended": recommended}
    selected_collection = set(collections[collection]) if collection in collections else None
    token = (query or "").strip().lower()
    filtered: list[Mapping[str, Any]] = []
    for module in modules:
        key = str(module["key"])
        searchable = " ".join((str(module.get("name", "")), str(module.get("purpose", "")), str(module.get("boundary", "")), CATEGORY_BY_MODULE[key], " ".join(module.get("record_types", [])))).lower()
        if token and token not in searchable:
            continue
        if category != "All categories" and CATEGORY_BY_MODULE[key] != category:
            continue
        if availability == "Available" and not module.get("can_create"):
            continue
        if availability == "View only" and module.get("can_create"):
            continue
        if selected_collection is not None and key not in selected_collection:
            continue
        filtered.append(module)

    if not filtered:
        if collection == "Favourites" and not favourites:
            empty_state("No favourite modules", "Your module launcher has no pinned Education Universe favourites.", icon="★", action_hint="Add a favourite from any module card.")
        elif collection == "Recent" and not recent:
            empty_state("No recent modules", "No Education Universe module has been opened in this session.", icon="◎", action_hint="Launch a module from the catalogue to begin.")
        else:
            empty_state("No modules match", "The current search and availability filters exclude every module.", icon="⌕", action_hint="Clear filters or use a broader query.")
        return

    by_key = {str(module["key"]): module for module in filtered}
    for category_name, category_keys in CATEGORIES:
        visible = [key for key in category_keys if key in by_key]
        if not visible:
            continue
        with st.expander(
            f"{category_name} · {len(visible)}",
            expanded=category != "All categories" or collection != "All modules",
            icon=":material/category:",
        ):
            for offset in range(0, len(visible), 2):
                columns = st.columns(2, gap="medium")
                for column, key in zip(columns, visible[offset : offset + 2]):
                    with column:
                        _module_card(by_key[key], scope, roles, totals, pending, demos)


def _create_record(universe: EducationUniverse, actor: str, institution_id: str, modules: list[Mapping[str, Any]], run: Run, scope: str) -> None:
    by_key = {str(module["key"]): module for module in modules}
    selected = st.selectbox(
        "Education module",
        list(by_key),
        format_func=lambda key: str(by_key[key]["name"]),
        key=f"{scope}_create_module",
    )
    module, definition = by_key[selected], _definition(selected)
    with st.container(border=True):
        st.subheader(f"{MODULE_ICONS.get(selected, ':material/apps:')} {module['name']}")
        st.write(str(module["purpose"]))
        st.warning(str(module["boundary"]), icon=":material/shield:")
        st.badge(
            "Creation available for your current role" if module.get("can_create") else "View only — educator or administrator permission required",
            icon=":material/verified_user:" if module.get("can_create") else ":material/lock:",
            color="green" if module.get("can_create") else "orange",
        )

    form_key = f"{scope}_guided_{selected}"
    with st.form(form_key, border=True):
        st.subheader("Create a guided workflow record")
        st.caption("Required fields come from the module definition. Enter only legitimate, reviewable information.")
        title = st.text_input("Record title", placeholder="Give this workflow a clear, descriptive name")
        record_type = st.selectbox("Record type", list(definition.record_types), format_func=_friendly)
        visibility_options = ["private", "restricted", "institution"]
        forced_restricted = selected in {"academic_erp", "question_bank", "safety_moderation"}
        if forced_restricted:
            visibility = "restricted"
            st.selectbox("Visibility", ["restricted"], disabled=True, help="This module enforces restricted visibility.")
        else:
            visibility = st.selectbox(
                "Visibility",
                visibility_options,
                index=visibility_options.index(definition.default_visibility),
                format_func=_friendly,
                help="The service applies institution and record-level read boundaries.",
            )
        st.markdown("**Required evidence**")
        payload = {field: _render_field(field, form_key) for field in definition.required_fields}
        notes = st.text_area("Additional context (optional)", placeholder="Background, reviewer context, or non-sensitive notes")
        if notes.strip():
            payload["notes"] = notes.strip()
        acknowledge = st.checkbox("I have not included payment-card data, protected answer keys, unsafe operational instructions, or unsupported claims.")
        submitted = st.form_submit_button(
            "Create durable record",
            type="primary",
            icon=":material/save:",
            disabled=not bool(module.get("can_create")),
        )

    if not submitted:
        return
    required_payload = {key: value for key, value in payload.items() if key in definition.required_fields}
    missing = [key for key, value in required_payload.items() if value is None or (isinstance(value, str) and not value.strip())]
    if not title.strip():
        st.error("Enter a record title.", icon=":material/error:")
    elif missing:
        st.error("Complete the required fields: " + ", ".join(_field_spec(field).label for field in missing), icon=":material/error:")
    elif not acknowledge:
        st.error("Confirm the safety and data boundary before saving.", icon=":material/gpp_maybe:")
    else:
        created = run(lambda: universe.create_record(actor, institution_id, selected, record_type, title, payload, visibility))
        if created:
            st.session_state[f"{scope}_record_id"] = created["id"]
            recent = [key for key in st.session_state.get(f"{scope}_recent", []) if key != selected]
            st.session_state[f"{scope}_recent"] = [selected, *recent][:6]
            st.success(f"Saved “{created['title']}” as a durable {_friendly(created['record_type'])} record.", icon=":material/check_circle:")
            st.caption(f"Workflow state: {_friendly(created['state'])} · Version {created['version']} · Visibility: {_friendly(created['visibility'])}")


def _record_label(record: Mapping[str, Any]) -> str:
    return f"{record.get('title', 'Untitled')} · {_friendly(str(record.get('state', '')))}"


def _records(universe: EducationUniverse, actor: str, modules: list[Mapping[str, Any]], records: list[Mapping[str, Any]], run: Run, scope: str) -> None:
    labels = {str(module["key"]): str(module["name"]) for module in modules}
    module_col, state_col = st.columns(2)
    with module_col:
        module_filter = st.selectbox("Module", ["", *labels], format_func=lambda key: "All modules" if not key else labels[key], key=f"{scope}_records_module")
    with state_col:
        states = sorted({str(record.get("state", "")) for record in records if record.get("state")})
        state_filter = st.multiselect("Workflow state", states, format_func=_friendly, key=f"{scope}_records_state")
    visible = [
        record for record in records
        if (not module_filter or record.get("module_key") == module_filter)
        and (not state_filter or record.get("state") in state_filter)
    ]
    if not visible:
        st.info(
            "No accessible persisted records match these filters." if records else "No accessible records exist yet. Create the first guided workflow record when your role permits it.",
            icon=":material/inbox:",
        )
        st.button("Create a record", icon=":material/add:", on_click=_switch_view, args=(scope, "Create record"))
        return

    st.dataframe(
        [{
            "Title": record.get("title"),
            "Module": labels.get(str(record.get("module_key")), _friendly(str(record.get("module_key", "")))),
            "Type": _friendly(str(record.get("record_type", ""))),
            "State": _friendly(str(record.get("state", ""))),
            "Visibility": _friendly(str(record.get("visibility", ""))),
            "Version": int(record.get("version") or 0),
            "Updated": record.get("updated_at"),
        } for record in visible],
        hide_index=True,
        column_config={
            "Title": st.column_config.TextColumn("Title", pinned=True),
            "Updated": st.column_config.DatetimeColumn("Updated", format="MMM DD, YYYY, h:mm a"),
        },
    )
    record_ids = [str(record["id"]) for record in visible]
    saved = str(st.session_state.get(f"{scope}_record_id", ""))
    selected_id = st.selectbox(
        "Review a record",
        record_ids,
        index=record_ids.index(saved) if saved in record_ids else 0,
        format_func=lambda record_id: _record_label(next(record for record in visible if record["id"] == record_id)),
        key=f"{scope}_review_record",
    )
    selected = next(record for record in visible if record["id"] == selected_id)
    with st.container(border=True):
        st.subheader(str(selected["title"]))
        with st.container(horizontal=True):
            st.badge(_friendly(str(selected["state"])), color="green" if selected["state"] in {"active", "published", "completed"} else "orange")
            st.badge(_friendly(str(selected["visibility"])), color="blue")
            st.badge(labels.get(str(selected["module_key"]), _friendly(str(selected["module_key"]))), color="gray")
        st.caption(f"Record ID: {selected['id']} · Version {selected['version']} · Owner: {selected['owner_id']}")
        st.warning(_definition(str(selected["module_key"])).boundary, icon=":material/shield:")
        evidence = [{"Evidence field": _field_spec(str(key)).label, "Value": "Yes" if value is True else "No" if value is False else str(value)} for key, value in (selected.get("payload") or {}).items()]
        if evidence:
            st.dataframe(evidence, hide_index=True)
        else:
            st.caption("This record has no visible evidence fields.")

    allowed = sorted(TRANSITIONS.get(str(selected["state"]), set()))
    if allowed:
        with st.form(f"{scope}_transition_{selected_id}"):
            st.subheader("Reviewed state transition")
            target = st.selectbox("Next workflow state", allowed, format_func=_friendly)
            note = st.text_area("Review note", placeholder="Record the evidence or reason for this transition")
            transition = st.form_submit_button("Apply transition", type="primary", icon=":material/published_with_changes:")
        if transition:
            changed = run(lambda: universe.transition_record(actor, selected_id, int(selected["version"]), target, note))
            if changed:
                st.success(f"Transitioned to {_friendly(changed['state'])}; the change was versioned and audited.", icon=":material/check_circle:")
                st.rerun()
    else:
        st.caption("This workflow state has no further transitions.")

    with st.expander("Audit history", icon=":material/history:"):
        history = run(lambda: universe.record_history(actor, selected_id)) or []
        if history:
            st.dataframe(
                [{"Event": _friendly(str(event.get("event_type", ""))), "From": _friendly(str(event.get("from_state", ""))), "To": _friendly(str(event.get("to_state", ""))), "Actor": event.get("actor_id"), "When": event.get("created_at")} for event in history],
                hide_index=True,
                column_config={"When": st.column_config.DatetimeColumn("When", format="MMM DD, YYYY, h:mm a")},
            )
        else:
            st.caption("No audit events are available for this record.")


def _readiness(modules: list[Mapping[str, Any]], dashboard: Mapping[str, Any], records: list[Mapping[str, Any]]) -> None:
    totals, pending, states = _counts(dashboard)
    demos = _demo_counts(records)
    st.subheader("Module readiness")
    with st.container(horizontal=True):
        st.metric("Definitions loaded", len(modules), border=True)
        st.metric("Available for this role", sum(bool(module.get("can_create")) for module in modules), border=True)
        st.metric("Modules in use", sum(totals.get(str(module["key"]), 0) > 0 for module in modules), border=True)
        st.metric("Pending offline sync", int(dashboard.get("pending_sync") or 0), border=True)

    with st.container(border=True):
        st.subheader(":material/checklist: Setup checklist")
        checklist = (
            ("Institution membership verified", bool(modules)),
            ("All 20 module definitions loaded", len(modules) == 20),
            ("Durable workflow storage reachable", "stored_counts" in dashboard),
            ("At least one guided record stored", sum(totals.values()) > 0),
            ("Demo records explicitly labelled", sum(demos.values()) > 0),
        )
        for label, complete in checklist:
            st.badge(label, icon=":material/check_circle:" if complete else ":material/radio_button_unchecked:", color="green" if complete else "gray")

    st.dataframe(
        [{
            "Module": module["name"],
            "Category": CATEGORY_BY_MODULE[str(module["key"])],
            "Availability": "Available" if module.get("can_create") else "View only",
            "Persisted records": totals.get(str(module["key"]), 0),
            "Demo records": demos.get(str(module["key"]), 0),
            "Pending actions": pending.get(str(module["key"]), 0),
        } for module in modules],
        hide_index=True,
        column_config={"Module": st.column_config.TextColumn("Module", pinned=True)},
    )

    module_col, state_col = st.columns(2)
    with module_col.container(border=True, height="stretch"):
        st.subheader("Persisted records by module")
        module_chart = [{"Module": str(module["name"]), "Records": totals.get(str(module["key"]), 0)} for module in modules if totals.get(str(module["key"]), 0) > 0]
        if module_chart:
            st.bar_chart(module_chart, x="Module", y="Records", horizontal=True)
        else:
            empty_state("No chart evidence yet", "The visual appears after a real versioned module record is stored.", icon="◫", action_hint="Create the first guided record in this module.")
    with state_col.container(border=True, height="stretch"):
        st.subheader("Workflow states")
        state_chart = [{"State": _friendly(state), "Records": count} for state, count in sorted(states.items()) if count > 0]
        if state_chart:
            st.bar_chart(state_chart, x="State", y="Records")
        else:
            empty_state("No workflow-state data", "No persisted records are available for the state distribution.", icon="↗", action_hint="Create and advance a module record through its workflow.")

    st.caption(str(dashboard.get("metric_definition", "Counts reflect durable, non-deleted Education Universe records.")))
    if not demos:
        st.info("Demo mode is not inferred from titles. No accessible records carry an explicit demo source status, so demo counts correctly remain zero.", icon=":material/science:")


def _live_engines(universe: EducationUniverse, actor: str, institution_id: str, roles: list[str], run: Run) -> None:
    from .module_engines import EducationModuleEngines

    engines = EducationModuleEngines(universe.platform)
    st.header("Live education engines")
    st.caption("Bounded, deterministic engines replace generic record-only demos for adaptive learning, analytics, virtual science, bioinformatics, assessment design and reproducibility.")
    tabs = st.tabs(["Adaptive learning", "Learning analytics", "Virtual lab", "Bioinformatics", "Assessment blueprint", "Reproducibility"])
    with tabs[0]:
        student_id = st.text_input("Student ID", value=actor, key="engine-adaptive-student")
        if st.button("Calculate mastery evidence", type="primary", key="engine-adaptive-run"):
            result = run(lambda: engines.adaptive_learning_snapshot(actor, institution_id, student_id))
            if result:
                rows = [{"Subject": item["subject"], "Mastery %": item["mastery_percent"], "Evidence confidence": item["evidence_confidence"], "Attendance": item["attendance_ratio"], "Assignment completion": item["assignment_completion_ratio"], "Released grade %": item["released_grade_percent"]} for item in result["subjects"]]
                st.dataframe(rows, hide_index=True, width="stretch")
                for item in result["subjects"]:
                    with st.expander(f"{item['subject']} recommendations"):
                        for recommendation in item["recommendations"]:
                            st.write(f"**{recommendation['action']}** — {recommendation['reason']}")
                st.info(result["explainability"], icon=":material/info:")
    with tabs[1]:
        analytics_student = st.text_input("Student ID", value=actor, key="engine-analytics-student")
        if st.button("Run explainable support review", type="primary", key="engine-analytics-run"):
            result = run(lambda: engines.learning_analytics(actor, institution_id, analytics_student))
            if result:
                st.metric("Subjects requiring human review", len(result["support_flags"]))
                st.dataframe(result["support_flags"], hide_index=True, width="stretch")
                st.info(result["metric_definition"], icon=":material/policy:")
    with tabs[2]:
        experiment = st.selectbox("Simulation", ["enzyme_kinetics", "logistic_population", "mendelian_monohybrid"], format_func=_friendly)
        parameters_text = st.text_area("Parameters (JSON)", value='{"substrate": 2, "vmax": 1, "km": 0.5}' if experiment == "enzyme_kinetics" else ('{"initial": 10, "rate": 0.2, "capacity": 100, "steps": 20}' if experiment == "logistic_population" else '{"parent_a": "Aa", "parent_b": "Aa"}'), key=f"engine-lab-{experiment}")
        if st.button("Run safe simulation", type="primary", key="engine-lab-run"):
            import json
            result = run(lambda: engines.virtual_lab(actor, institution_id, experiment, json.loads(parameters_text)))
            if result: st.json(result)
    with tabs[3]:
        operation = st.selectbox("Operation", ["fasta_stats", "reverse_complement", "translate"], format_func=_friendly)
        sequence = st.text_area("DNA or FASTA sequence", value=">example\nATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG", height=140)
        if st.button("Run bounded analysis", type="primary", key="engine-bio-run"):
            result = run(lambda: engines.bioinformatics_sandbox(actor, institution_id, operation, sequence))
            if result: st.json(result)
    with tabs[4]:
        staff = bool(set(roles) & {"platform_administrator", "institution_administrator", "principal", "dean", "registrar", "department_head", "examination_controller", "subject_teacher", "class_teacher", "lecturer", "assistant_professor", "professor", "teaching_assistant", "laboratory_instructor", "academic_mentor", "class_coordinator"})
        if not staff:
            st.info("Assessment blueprint creation is available to authorized educators.", icon=":material/lock:")
        else:
            subjects = run(lambda: universe.platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? ORDER BY code", (institution_id,))) or []
            if subjects:
                subject_id = st.selectbox("Subject", [item["id"] for item in subjects], format_func=lambda value: next(f"{item['code']} · {item['name']}" for item in subjects if item["id"] == value))
                outcomes = st.text_area("Learning outcomes, one per line", "Explain core concepts\nApply the method\nInterpret evidence")
                total_marks = st.number_input("Total marks", min_value=1.0, value=100.0)
                if st.button("Generate review blueprint", type="primary", key="engine-blueprint-run"):
                    result = run(lambda: engines.assessment_blueprint(actor, institution_id, subject_id, outcomes.splitlines(), total_marks))
                    if result: st.json(result)
            else:
                st.info("Create a subject before generating an assessment blueprint.", icon=":material/quiz:")
    with tabs[5]:
        method = st.text_area("Method")
        provenance = st.text_area("Provenance")
        license_name = st.text_input("Licence")
        software = st.text_input("Software versions", placeholder="Python 3.11; BioIntel 15.6.0")
        parameters = st.text_area("Parameters JSON", "{}")
        checksums = st.text_area("Checksums JSON", "{}")
        private_removed = st.checkbox("Private student data removed", value=True)
        if st.button("Check reproducibility readiness", type="primary", key="engine-repro-run"):
            import json
            package = {"method": method, "provenance": provenance, "license": license_name, "software_versions": [value.strip() for value in software.split(";") if value.strip()], "parameters": json.loads(parameters), "checksums": json.loads(checksums), "contains_private_data": not private_removed}
            result = run(lambda: engines.reproducibility_check(actor, institution_id, package))
            if result:
                st.metric("Readiness score", f"{result['score_percent']}%")
                st.json(result)


def render_universe_workspace(
    universe: EducationUniverse,
    actor: str,
    institution_id: str,
    run: Run,
) -> None:
    """Render the role-aware Education Universe with Phase 2 visual intelligence."""
    from .phase2 import EducationPhase2
    from .phase2_ui import (
        render_advanced_command_center,
        render_branding_center,
        render_module_visual_studio,
        render_presentation_launcher,
        render_presentation_mode,
        render_report_center,
    )

    service = EducationPhase2(universe.platform)
    if st.session_state.get("education_presentation_mode", False):
        render_presentation_mode(service, actor, institution_id, run)
        return

    scope = _scope(actor, institution_id)
    _initialise(scope)
    dashboard = run(lambda: universe.dashboard(actor, institution_id)) or {}
    modules = run(lambda: universe.modules(actor, institution_id)) or []
    records = run(lambda: universe.list_records(actor, institution_id, limit=500)) or []
    memberships = run(lambda: universe.platform.membership(actor, institution_id)) or []
    roles = [str(item["role"]) for item in memberships]
    if not modules:
        st.error("The Education Universe registry is unavailable for this institution or role.", icon=":material/error:")
        return

    render_advanced_command_center(service, actor, institution_id, run)
    _workspace_summary(dashboard, modules, records)
    options = ["Module hub", "Live engines", "Visual studio", "Create record", "Records", "Readiness", "Report center", "Branding", "Presentation"]
    state_key = f"{scope}_view"
    if st.session_state.get(state_key) not in options:
        st.session_state[state_key] = "Module hub"
    st.segmented_control("Workspace", options, key=state_key)
    view = str(st.session_state.get(state_key, "Module hub"))
    if view == "Module hub":
        _module_hub(modules, roles, dashboard, records, scope)
    elif view == "Live engines":
        _live_engines(universe, actor, institution_id, roles, run)
    elif view == "Visual studio":
        render_module_visual_studio(service, actor, institution_id, run)
    elif view == "Create record":
        _create_record(universe, actor, institution_id, modules, run, scope)
    elif view == "Records":
        _records(universe, actor, modules, records, run, scope)
    elif view == "Readiness":
        _readiness(modules, dashboard, records)
    elif view == "Report center":
        render_report_center(service, actor, institution_id, run)
    elif view == "Branding":
        render_branding_center(service, actor, institution_id, run)
    else:
        render_presentation_launcher(service, actor, institution_id, run)


__all__ = ["render_universe_workspace"]





