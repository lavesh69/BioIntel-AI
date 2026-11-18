from __future__ import annotations

from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_app_navigation, render_role_snapshot, render_workspace_context
from .phase11 import ADMIN_ROLES, TEACHER_ROLES
from .phase15 import EducationPhase15Service
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run
from biointel.ui.frontend_v10 import empty_state, kpi_grid, section_header


def _roles(platform: Any, actor: str, institution_id: str) -> set[str]:
    return {str(row["role"]) for row in platform.membership(actor, institution_id)}


def _overview(service: EducationPhase15Service, actor: str, institution_id: str) -> None:
    posture = _run(lambda: service.phase15_posture(actor, institution_id)) or {"counts": {}}
    counts = posture.get("counts", {})
    kpi_grid([
        (":material/cell_tower:", "Durable events", counts.get("events", 0), "SSE-ready institution event stream"),
        (":material/hub:", "Hybrid indexes", counts.get("rag_indexes", 0), "BM25 plus local semantic vectors"),
        (":material/smart_toy:", "Verified model runtimes", counts.get("verified_model_runtimes", 0), "Live-qualified local or opt-in endpoints"),
        (":material/science:", "Provider records", counts.get("pulse_records", 0), "Normalised Science Pulse evidence"),
        (":material/video_library:", "Media assets", counts.get("media_assets", 0), "Server-governed Academy media"),
    ])
    section_header("Production runtime truth boundary", "Implemented local controls are separated from credentials, external infrastructure and independent qualification.", icon=":material/verified_user:")
    for item in posture.get("qualification_boundaries", []):
        st.info(item)


def _events(service: EducationPhase15Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Durable real-time event stream", "Publish institution-scoped events and inspect the same cursor-based stream exposed through the Phase 15 SSE API.", icon=":material/cell_tower:")
    if roles & TEACHER_ROLES:
        with st.form("phase15-event-publish"):
            channel = st.text_input("Channel", value="education-operations")
            event_type = st.text_input("Event type", value="status_changed")
            target_type = st.text_input("Target type", value="workspace")
            target_id = st.text_input("Target ID")
            message = st.text_area("Message or summary")
            role_audience = st.multiselect("Audience roles", sorted(TEACHER_ROLES | {"university_student", "college_student", "school_student", "parent_guardian"}))
            submitted = st.form_submit_button("Publish governed event", type="primary", icon=":material/send:")
        if submitted:
            result = _run(lambda: service.publish_event(actor, institution_id, channel=channel, event_type=event_type, target_type=target_type, target_id=target_id, payload={"message": message}, audience={"roles": role_audience}))
            if result:
                st.success(f"Event {result['sequence']} published.")
    after = st.number_input("After sequence", min_value=0, value=0, step=1)
    channels = st.text_input("Channel filter (comma separated)")
    result = _run(lambda: service.poll_events(actor, institution_id, after_sequence=int(after), channels=[value.strip() for value in channels.split(",") if value.strip()], limit=200)) or {"events": []}
    if result.get("events"):
        st.dataframe(result["events"], width="stretch", hide_index=True)
    else:
        empty_state("No visible events", "Publish an event or wait for an institution workflow to emit one.", icon="📡", action_hint="The SSE endpoint uses the same durable sequence cursor.")


def _rag(service: EducationPhase15Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Hybrid semantic evidence retrieval", "Build a deterministic local vector index over approved evidence, then combine BM25 and cosine similarity with permission filtering.", icon=":material/hub:")
    projects = platform._all("SELECT DISTINCT project_id FROM education_rag_documents WHERE institution_id=? AND state='approved' ORDER BY project_id", (institution_id,))
    if not projects:
        empty_state("No approved RAG project", "Register, review and ingest an evidence document in Local Autonomy first.", icon="🧠")
        return
    project_id = st.selectbox("Evidence project", [row["project_id"] for row in projects])
    if roles & TEACHER_ROLES:
        with st.expander("Build or refresh hybrid index", expanded=False):
            dimensions = st.select_slider("Vector dimensions", options=[128, 256, 384, 512, 768], value=384)
            if st.button("Build local semantic index", type="primary", icon=":material/account_tree:"):
                result = _run(lambda: service.build_hybrid_rag_index(actor, institution_id, project_id, dimensions=int(dimensions)))
                if result:
                    st.success(f"Indexed {result['chunk_count']} approved chunks.")
    with st.form("phase15-hybrid-search"):
        query = st.text_input("Evidence question", placeholder="Which evidence discusses DNA repair?")
        vector_weight = st.slider("Semantic weight", 0.0, 1.0, 0.55, 0.05)
        submitted = st.form_submit_button("Search approved evidence", type="primary", icon=":material/search:")
    if submitted:
        st.session_state.phase15_hybrid_results = _run(lambda: service.hybrid_rag_search(actor, institution_id, project_id, query, vector_weight=float(vector_weight)))
    result = st.session_state.get("phase15_hybrid_results") or {}
    for row in result.get("results", []):
        with st.container(border=True):
            st.markdown(f"#### {row['document_title']}")
            st.caption(f"{row['citation']} · hybrid {row['score']:.3f} · lexical {row['lexical_score']:.3f} · semantic {row['vector_score']:.3f}")
            st.write(row["excerpt"])
            st.code(row["document_sha256"], language=None)


def _models(service: EducationPhase15Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Local and opt-in model runtime manager", "Verify Ollama, OpenAI-compatible or llama.cpp runtimes before use; remote processing requires explicit per-request consent.", icon=":material/smart_toy:")
    if roles & ADMIN_ROLES:
        with st.expander("Register model runtime", expanded=False):
            with st.form("phase15-model-runtime"):
                name = st.text_input("Runtime name")
                provider = st.selectbox("Provider", ["ollama", "openai_compatible", "llama_cpp"])
                endpoint = st.text_input("Endpoint or executable", value="http://127.0.0.1:11434" if provider != "llama_cpp" else "")
                model = st.text_input("Model name")
                secret = st.text_input("Secret reference", placeholder="env:BIOINTEL_MODEL_TOKEN")
                external = st.checkbox("Remote/external processing")
                submitted = st.form_submit_button("Register runtime", type="primary", icon=":material/add:")
            if submitted:
                result = _run(lambda: service.register_model_runtime(actor, institution_id, name=name, provider_type=provider, model_name=model, endpoint=endpoint, secret_reference=secret, external_processing=external))
                if result:
                    st.success("Runtime registered; live verification is still required.")
    runtimes = platform._all("SELECT * FROM education_model_runtimes WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    if not runtimes:
        empty_state("No model runtime", "Register a local Ollama or another governed runtime.", icon="🤖")
        return
    st.dataframe(runtimes, width="stretch", hide_index=True)
    runtime_id = st.selectbox("Selected runtime", [row["id"] for row in runtimes], format_func=lambda value: next(f"{row['name']} · {row['provider_type']} · {row['state']}" for row in runtimes if row["id"] == value))
    if roles & ADMIN_ROLES and st.button("Run live verification", icon=":material/fact_check:"):
        result = _run(lambda: service.verify_model_runtime(actor, runtime_id))
        if result:
            st.success(f"Verification state: {result['state']}")
            st.json(result)
    with st.form("phase15-model-generate"):
        prompt = st.text_area("Prompt", placeholder="Use only approved evidence and explain the concept.")
        allow_external = st.checkbox("I explicitly approve external processing for this request")
        submitted = st.form_submit_button("Generate through verified runtime", type="primary", icon=":material/play_arrow:")
    if submitted:
        result = _run(lambda: service.generate_with_runtime(actor, runtime_id, prompt, allow_external_processing=allow_external))
        if result:
            st.markdown(result["text"])
            st.caption(f"{result['model']} · {result['latency_ms']} ms")


def _pulse(service: EducationPhase15Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Built-in Science Pulse providers", "Normalise PubMed, Europe PMC, Crossref, OpenAlex and arXiv metadata with cursor checkpoints and institution-level deduplication.", icon=":material/science:")
    if roles & ADMIN_ROLES:
        with st.form("phase15-pulse-config"):
            provider = st.selectbox("Provider", ["pubmed", "europe_pmc", "crossref", "openalex", "arxiv"])
            name = st.text_input("Configuration name", value="Biotechnology intelligence")
            query = st.text_input("Search query", value="bioinformatics")
            submitted = st.form_submit_button("Save provider", type="primary", icon=":material/add_link:")
        if submitted:
            result = _run(lambda: service.configure_pulse_provider(actor, institution_id, provider=provider, name=name, query=query))
            if result:
                st.success("Provider configured.")
    configs = platform._all("SELECT * FROM education_pulse_provider_configs WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    if not configs:
        empty_state("No provider configured", "Add a public Science Pulse provider to begin metadata synchronization.", icon="🧬")
        return
    config_id = st.selectbox("Provider configuration", [row["id"] for row in configs], format_func=lambda value: next(f"{row['provider']} · {row['name']}" for row in configs if row["id"] == value))
    if roles & ADMIN_ROLES and st.button("Synchronize provider", type="primary", icon=":material/sync:"):
        result = _run(lambda: service.sync_pulse_provider(actor, config_id, limit=25))
        if result:
            st.success(f"{result['state']} · received {result['received_count']} · inserted {result['inserted_count']}")
    records = platform._all("SELECT provider,external_id,doi,pmid,title,published_at,record_type,source_url FROM education_pulse_external_records WHERE institution_id=? ORDER BY updated_at DESC LIMIT 250", (institution_id,))
    if records:
        st.dataframe(records, width="stretch", hide_index=True, column_config={"source_url": st.column_config.LinkColumn("Source")})
    else:
        empty_state("No normalized records", "Run the first provider synchronization.", icon="⌁")


def _media(service: EducationPhase15Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Academy media telemetry", "Register verified lecture media and inspect server-observed playback evidence that does not count seek-only jumps.", icon=":material/video_library:")
    lectures = platform._all("SELECT id,title,course_id,duration_seconds,processing_state,state FROM lectures WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    if not lectures:
        empty_state("No Academy lecture", "Create a course and lecture in Academy first.", icon="🎬")
        return
    lecture_id = st.selectbox("Lecture", [row["id"] for row in lectures], format_func=lambda value: next(f"{row['title']} · {row['state']}" for row in lectures if row["id"] == value))
    if roles & TEACHER_ROLES:
        with st.form("phase15-media-register"):
            source_path = st.text_input("Governed local video path")
            probe = st.checkbox("Probe with ffprobe when available", value=True)
            submitted = st.form_submit_button("Register media asset", type="primary", icon=":material/video_file:")
        if submitted:
            result = _run(lambda: service.register_media_asset(actor, lecture_id, source_path, probe=probe))
            if result:
                st.success(f"Media registered · {result['processing_state']}")
    try:
        summary = service.playback_summary(actor, lecture_id)
    except Exception:
        summary = None
    if summary:
        kpi_grid([
            (":material/timer:", "Observed watch", f"{summary['observed_watch_seconds']:.1f}s", "Plausible server-observed intervals"),
            (":material/forward_media:", "Max position", f"{summary['max_position_seconds']:.1f}s", "Seek position is tracked separately"),
            (":material/task_alt:", "Complete", "Yes" if summary["completed"] else "No", "Course threshold and telemetry policy"),
        ])
        st.caption(summary["policy"])
    events = platform._all("SELECT event_type,position_seconds,playback_rate,session_id,created_at FROM education_media_playback_events_v15 WHERE institution_id=? AND lecture_id=? ORDER BY created_at DESC LIMIT 200", (institution_id, lecture_id))
    if events:
        st.dataframe(events, width="stretch", hide_index=True)


def render_academy_media_telemetry(
    root: Path, platform: Any, actor: str, institution_id: str
) -> None:
    """Expose governed Academy media registration and playback evidence in Academy."""
    _media(
        EducationPhase15Service(platform, root=root),
        platform,
        actor,
        institution_id,
        _roles(platform, actor, institution_id),
    )


def render_phase15_runtime_and_research_center(root: Path) -> None:
    render_app_header(
        "runtime",
        "BioIntel Production Runtime & Research Intelligence Center",
        "Durable events, hybrid semantic evidence, governed model runtimes, built-in Science Pulse providers and server-observed Academy media telemetry.",
        eyebrow="BIOINTEL PHASE 15 · RUNTIME & RESEARCH",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Production Runtime user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    service = EducationPhase15Service(platform, root=root)
    roles = _roles(platform, actor, institution_id)
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    render_app_navigation("runtime", platform, actor, institution_id)
    workspace = st.segmented_control(
        "Runtime and research workspace",
        ["Overview", "Live Events", "Hybrid RAG", "Model Runtime", "Science Providers", "Media Telemetry"],
        default="Overview",
        key=f"phase15-workspace-{actor}-{institution_id}",
    )
    if workspace == "Live Events":
        _events(service, platform, actor, institution_id, roles)
    elif workspace == "Hybrid RAG":
        _rag(service, platform, actor, institution_id, roles)
    elif workspace == "Model Runtime":
        _models(service, platform, actor, institution_id, roles)
    elif workspace == "Science Providers":
        _pulse(service, platform, actor, institution_id, roles)
    elif workspace == "Media Telemetry":
        _media(service, platform, actor, institution_id, roles)
    else:
        _overview(service, actor, institution_id)
