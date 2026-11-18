from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_app_navigation, render_role_snapshot, render_workspace_context
from .phase11 import ADMIN_ROLES, TEACHER_ROLES
from .phase16 import EducationPhase16Service
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run
from biointel.ui.frontend_v10 import empty_state, kpi_grid, section_header


def _roles(platform: Any, actor: str, institution_id: str) -> set[str]:
    return {str(row["role"]) for row in platform.membership(actor, institution_id)}


def _overview(service: EducationPhase16Service, actor: str, institution_id: str) -> None:
    posture = _run(lambda: service.phase16_posture(actor, institution_id)) or {"counts": {}}
    counts = posture.get("counts", {})
    kpi_grid([
        (":material/cell_tower:", "Live consumers", counts.get("event_consumers", 0), "Durable cursors and presence"),
        (":material/fact_check:", "RAG evaluation cases", counts.get("rag_evaluation_cases", 0), "Recall and reciprocal-rank evidence"),
        (":material/notifications_active:", "Research alert rules", counts.get("pulse_alert_rules", 0), "Saved scientific evidence watches"),
        (":material/biotech:", "Scientific datasets", counts.get("scientific_datasets", 0), "Bounded FASTA/FASTQ workbenches"),
        (":material/movie_filter:", "Media jobs", counts.get("media_processing_jobs", 0), "FFmpeg-qualified output pipeline"),
        (":material/subtitles:", "Transcription jobs", counts.get("transcription_jobs", 0), "Bundled multilingual local model"),
    ])
    section_header("Completion posture", "Local controls are operational; external infrastructure remains evidence-bound.", icon=":material/verified:")
    for item in posture.get("implemented", []):
        st.success(item, icon=":material/check_circle:")
    for item in posture.get("qualification_boundaries", []):
        st.info(item)


def _events(service: EducationPhase16Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Event consumers and presence", "Register durable desktop/service consumers, consume visible events once, and maintain replay-safe cursors.", icon=":material/cell_tower:")
    with st.form("phase16-consumer"):
        key = st.text_input("Consumer key", value="education-desktop")
        submitted = st.form_submit_button("Register or refresh consumer", type="primary", icon=":material/add:")
    if submitted:
        result = _run(lambda: service.register_event_consumer(actor, institution_id, consumer_key=key, metadata={"surface": "phase16-ui"}))
        if result:
            st.session_state.phase16_consumer = result["id"]
            st.success("Consumer is active.")
    consumers = platform._all("SELECT id,actor_id,consumer_key,last_sequence,state,heartbeat_at FROM education_event_consumers_v16 WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    if not consumers:
        empty_state("No event consumer", "Register a desktop or worker consumer to keep a durable replay cursor.", icon="📡")
        return
    st.dataframe(consumers, width="stretch", hide_index=True)
    consumer_id = st.selectbox("Consumer", [row["id"] for row in consumers], format_func=lambda value: next(f"{row['consumer_key']} · {row['actor_id']} · seq {row['last_sequence']}" for row in consumers if row["id"] == value))
    cols = st.columns(2)
    if cols[0].button("Consume and acknowledge", type="primary", icon=":material/download:"):
        result = _run(lambda: service.consume_events(actor, consumer_id, limit=100, acknowledge=True))
        if result is not None:
            st.session_state.phase16_events = result
    if cols[1].button("Heartbeat", icon=":material/favorite:"):
        if _run(lambda: service.heartbeat_event_consumer(actor, consumer_id)):
            st.success("Presence heartbeat recorded.")
    events = (st.session_state.get("phase16_events") or {}).get("events", [])
    if events:
        st.dataframe(events, width="stretch", hide_index=True)
    if roles & ADMIN_ROLES:
        with st.expander("Retention cleanup"):
            days = st.number_input("Retention days", 1, 3650, 14)
            if st.button("Clean expired and old events", icon=":material/delete_sweep:"):
                result = _run(lambda: service.cleanup_event_stream(actor, institution_id, retention_days=int(days)))
                if result: st.json(result)


def _rag(service: EducationPhase16Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("RAG diversity and evaluation", "Use MMR to reduce redundant evidence and measure recall@k and reciprocal rank against human-authored cases.", icon=":material/fact_check:")
    projects = [row["project_id"] for row in platform._all("SELECT DISTINCT project_id FROM education_rag_vector_indexes WHERE institution_id=? AND state='ready' ORDER BY project_id", (institution_id,))]
    if not projects:
        empty_state("No ready hybrid index", "Approve and index evidence in the Runtime & Research Center first.", icon="◇")
        return
    project = st.selectbox("Evidence project", projects)
    with st.form("phase16-advanced-search"):
        query = st.text_input("Question", value="DNA repair and genome stability")
        diversity = st.slider("Diversity weight", 0.0, 0.8, 0.25, 0.05)
        submitted = st.form_submit_button("Run diverse evidence search", type="primary", icon=":material/search:")
    if submitted:
        st.session_state.phase16_search = _run(lambda: service.advanced_rag_search(actor, institution_id, project, query, diversity_weight=float(diversity)))
    for row in (st.session_state.get("phase16_search") or {}).get("results", []):
        with st.container(border=True):
            st.markdown(f"#### {row['rank']}. {row['document_title']}")
            st.caption(f"{row['citation']} · score {row['score']:.3f} · MMR {row['mmr_score']:.3f}")
            st.write(row["excerpt"])
    if roles & TEACHER_ROLES:
        with st.expander("Create evaluation case", expanded=False):
            with st.form("phase16-rag-case"):
                case_query = st.text_input("Evaluation query")
                expected_docs = st.text_input("Expected document IDs", help="Comma-separated approved document IDs")
                submitted_case = st.form_submit_button("Save evaluation case", icon=":material/add_task:")
            if submitted_case:
                result = _run(lambda: service.create_rag_evaluation_case(actor, institution_id, project_id=project, query=case_query, expected_document_ids=[value.strip() for value in expected_docs.split(",") if value.strip()]))
                if result: st.success("Evaluation case saved.")
        if st.button("Run retrieval evaluation", type="primary", icon=":material/analytics:"):
            result = _run(lambda: service.run_rag_evaluation(actor, institution_id, project, top_k=5))
            if result:
                kpi_grid([
                    (":material/target:", "Recall@5", f"{result['recall_at_k']:.1%}", "Expected evidence found"),
                    (":material/format_list_numbered:", "MRR", f"{result['mean_reciprocal_rank']:.3f}", "First relevant result rank"),
                    (":material/check_circle:", "Grounded", f"{result['grounded_rate']:.1%}", "Cases with evidence"),
                ])
                st.dataframe(result["details"], width="stretch", hide_index=True)


def _alerts(service: EducationPhase16Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Science Pulse saved alerts", "Create governed evidence watches and turn normalized provider records into a reviewable alert inbox.", icon=":material/notifications_active:")
    if roles & TEACHER_ROLES:
        with st.form("phase16-pulse-alert"):
            name = st.text_input("Alert name", value="Genome editing watch")
            terms = st.text_input("Required terms", value="CRISPR, genome editing")
            providers = st.multiselect("Providers", ["pubmed", "europe_pmc", "crossref", "openalex", "arxiv"])
            submitted = st.form_submit_button("Save alert rule", type="primary", icon=":material/add_alert:")
        if submitted:
            result = _run(lambda: service.create_pulse_alert_rule(actor, institution_id, name=name, query_terms=[value.strip() for value in terms.split(",") if value.strip()], providers=providers))
            if result: st.success("Research alert rule saved.")
        if st.button("Evaluate current provider records", type="primary", icon=":material/radar:"):
            result = _run(lambda: service.evaluate_pulse_alerts(actor, institution_id))
            if result: st.success(f"{result['new_hits']} new evidence alerts created.")
    hits = _run(lambda: service.pulse_alert_hits(actor, institution_id)) or []
    if not hits:
        empty_state("No research alerts", "Create a saved watch and synchronize Science Pulse providers.", icon="🔔")
        return
    st.dataframe(hits, width="stretch", hide_index=True, column_config={"source_url": st.column_config.LinkColumn("Source")})
    unread = [row for row in hits if row["state"] == "unread"]
    if unread:
        hit_id = st.selectbox("Unread alert", [row["id"] for row in unread], format_func=lambda value: next(row["title"] for row in unread if row["id"] == value))
        if st.button("Mark selected alert read", icon=":material/done_all:"):
            if _run(lambda: service.mark_pulse_alert_read(actor, hit_id)): st.success("Alert reviewed.")


def _scientific(service: EducationPhase16Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Bounded sequence workbench", "Run local FASTA/FASTQ quality control, translation, ORF, k-mer and pairwise alignment with reproducible JSON artifacts.", icon=":material/biotech:")
    if roles & TEACHER_ROLES:
        with st.form("phase16-dataset"):
            path = st.text_input("FASTA/FASTQ local path")
            name = st.text_input("Dataset name")
            submitted = st.form_submit_button("Register governed dataset", type="primary", icon=":material/upload_file:")
        if submitted:
            result = _run(lambda: service.register_scientific_dataset(actor, institution_id, path, name=name))
            if result: st.success(f"Dataset registered · {result['record_count']} records")
    datasets = platform._all("SELECT id,name,source_name,format,record_count,size_bytes,created_at FROM education_scientific_datasets_v16 WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
    if not datasets:
        empty_state("No sequence dataset", "Register a bounded FASTA or FASTQ file to open the scientific workbench.", icon="🧬")
        return
    st.dataframe(datasets, width="stretch", hide_index=True)
    dataset_id = st.selectbox("Dataset", [row["id"] for row in datasets], format_func=lambda value: next(f"{row['name']} · {row['format']} · {row['record_count']} records" for row in datasets if row["id"] == value))
    analysis = st.selectbox("Analysis", ["qc", "translate", "orf", "kmer", "alignment"])
    params: dict[str, Any] = {}
    if analysis == "translate": params["frame"] = st.number_input("Frame (0–2)", 0, 2, 0)
    elif analysis == "orf": params["minimum_aa"] = st.number_input("Minimum amino acids", 5, 5000, 20)
    elif analysis == "kmer": params["k"] = st.number_input("k-mer length", 1, 12, 3)
    if st.button("Run scientific analysis", type="primary", icon=":material/play_arrow:"):
        result = _run(lambda: service.run_sequence_analysis(actor, dataset_id, analysis_type=analysis, parameters=params))
        if result:
            st.success(f"Completed · evidence {result['artifact_sha256'][:16]}…")
            st.json(result["result"])


def _media(service: EducationPhase16Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("FFmpeg media pipeline", "Plan thumbnails, 720p MP4 or HLS outputs; execution only passes when the local FFmpeg process produces verified files.", icon=":material/movie_filter:")
    readiness = service.transcription_readiness()
    if readiness["ready"]:
        st.success(
            f"Offline multilingual transcription ready · faster-whisper {readiness['package_version']} · "
            f"model {readiness['model_manifest_sha256'][:12]}…",
            icon=":material/subtitles:",
        )
        st.caption("Runtime network access and API credentials are not required. Educator review is required before publication or Shiro indexing.")
    else:
        st.warning(readiness.get("reason") or "Local transcription configuration is incomplete.", icon=":material/settings:")
    assets = platform._all("SELECT id,lecture_id,source_path,duration_seconds,processing_state,created_at FROM education_media_assets_v15 WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
    if not assets:
        empty_state("No governed media asset", "Register lecture media in Runtime & Research first.", icon="🎞️")
        return
    st.dataframe(assets, width="stretch", hide_index=True)
    asset_id = st.selectbox("Media asset", [row["id"] for row in assets])
    profile = st.selectbox("Output profile", ["thumbnail", "mp4_720p", "hls_720p"])
    if roles & TEACHER_ROLES and st.button("Plan media job", type="primary", icon=":material/add_to_queue:"):
        result = _run(lambda: service.plan_media_processing(actor, asset_id, profile=profile))
        if result: st.success(f"Job planned · {result['id']}")
    jobs = platform._all("SELECT id,asset_id,profile,state,progress,output_dir,error_text,updated_at FROM education_media_processing_jobs_v16 WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    if jobs:
        st.dataframe(jobs, width="stretch", hide_index=True)
        executable = [row for row in jobs if row["state"] in {"planned", "failed"}]
        if roles & TEACHER_ROLES and executable:
            job_id = st.selectbox("Executable job", [row["id"] for row in executable])
            if st.button("Execute with local FFmpeg", icon=":material/play_circle:"):
                result = _run(lambda: service.execute_media_processing(actor, job_id))
                if result: st.success(f"Processing state: {result['state']}")


    section_header(
        "Offline lecture transcription",
        "Create a durable job from governed media, then execute the bundled multilingual model without external credentials.",
        icon=":material/subtitles:",
    )
    lecture_rows = platform._all(
        """SELECT l.id,l.title,l.state,a.id asset_id,a.source_path
           FROM lectures l JOIN education_media_assets_v15 a ON a.lecture_id=l.id
           WHERE l.institution_id=? ORDER BY l.updated_at DESC""",
        (institution_id,),
    )
    if lecture_rows:
        lecture_by_id = {row["id"]: row for row in lecture_rows}
        selected_lecture = st.selectbox(
            "Lecture to transcribe",
            list(lecture_by_id),
            format_func=lambda value: lecture_by_id[value]["title"],
        )
        language = st.selectbox("Transcript language", ["Auto", "English", "Hindi", "Hinglish"])
        if roles & TEACHER_ROLES and st.button(
            "Plan offline transcription",
            type="primary",
            icon=":material/queue:",
            disabled=not readiness["ready"],
        ):
            result = _run(
                lambda: service.plan_lecture_transcription(
                    actor, selected_lecture, language=language.casefold()
                )
            )
            if result:
                st.success(f"Transcription job {result['id']} · {result['state']}")
    transcription_jobs = service.transcription_jobs(actor, institution_id)
    if transcription_jobs:
        st.dataframe(
            [
                {
                    "id": row["id"],
                    "lecture_id": row["lecture_id"],
                    "language": row["requested_language"],
                    "detected": row["detected_language"],
                    "state": row["state"],
                    "progress": row["progress"],
                    "error": row["error_text"],
                    "updated_at": row["updated_at"],
                }
                for row in transcription_jobs
            ],
            width="stretch",
            hide_index=True,
        )
        executable_transcripts = [row for row in transcription_jobs if row["state"] in {"planned", "failed"}]
        if roles & TEACHER_ROLES and executable_transcripts:
            transcript_job = st.selectbox(
                "Executable transcription job",
                [row["id"] for row in executable_transcripts],
            )
            if st.button("Execute offline transcription", icon=":material/play_circle:"):
                with st.spinner("Transcribing locally. Long lectures can take several minutes…"):
                    result = _run(lambda: service.execute_lecture_transcription(actor, transcript_job))
                if result:
                    st.success("A real transcript candidate was generated. Human approval is required before it becomes a student or Shiro source.")
        reviewable = [row for row in transcription_jobs if row["state"] == "review_required"]
        if roles & TEACHER_ROLES and reviewable:
            review_job = st.selectbox(
                "Transcript candidate awaiting review",
                [row["id"] for row in reviewable],
            )
            candidate = _run(lambda: service.transcription_candidate(actor, review_job))
            if candidate:
                st.caption(
                    f"Detected {candidate['detected_language'] or 'unknown'} · "
                    f"confidence {float(candidate['language_probability']):.2f} · "
                    f"source {candidate['source_sha256'][:12]}…"
                )
                st.text_area(
                    "Generated transcript candidate",
                    value=str(candidate["text"]),
                    height=240,
                    disabled=True,
                )
                with st.form(f"transcription-review-{review_job}"):
                    decision = st.selectbox("Human review decision", ["Approve", "Reject"])
                    replace_existing = st.checkbox(
                        "Explicitly replace an existing approved transcript in this language",
                        value=False,
                    )
                    reason = st.text_area("Review note or rejection reason")
                    submitted_review = st.form_submit_button(
                        "Record human decision",
                        type="primary",
                        icon=":material/fact_check:",
                    )
                if submitted_review:
                    if decision == "Approve":
                        reviewed = _run(
                            lambda: service.approve_lecture_transcription(
                                actor,
                                review_job,
                                replace_existing=replace_existing,
                            )
                        )
                        if reviewed:
                            st.success("Transcript approved and published to the lecture evidence boundary.")
                    else:
                        reviewed = _run(
                            lambda: service.reject_lecture_transcription(
                                actor,
                                review_job,
                                reason=reason,
                            )
                        )
                        if reviewed:
                            st.info("Transcript candidate rejected; no student or Shiro transcript was published.")
    elif not lecture_rows:
        st.info("Upload and register real lecture media before planning transcription.")

def render_academy_media_pipeline(
    root: Path, platform: Any, actor: str, institution_id: str
) -> None:
    """Expose verified FFmpeg jobs within the Academy Lecture Studio."""
    _media(
        EducationPhase16Service(platform, root=root),
        platform,
        actor,
        institution_id,
        _roles(platform, actor, institution_id),
    )


def render_phase16_completion_center(root: Path) -> None:
    render_app_header(
        "completion16",
        "BioIntel Final Runtime, Evidence & Scientific Workbench Center",
        "Replay-safe live consumers, measurable RAG quality, saved scientific alerts, bounded sequence analytics and verified media processing.",
        eyebrow="BIOINTEL PHASE 16 · FINAL LOCAL COMPLETION",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Phase 16 user ID", demo_mode)
    actor = _actor(); institution_id = _institution(platform)
    if not institution_id: return
    service = EducationPhase16Service(platform, root=root)
    roles = _roles(platform, actor, institution_id)
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    render_app_navigation("completion16", platform, actor, institution_id)
    workspace = st.segmented_control(
        "Completion workspace",
        ["Overview", "Live Consumers", "RAG Quality", "Research Alerts", "Scientific Workbench", "Media Pipeline"],
        default="Overview",
        key=f"phase16-workspace-{actor}-{institution_id}",
    )
    if workspace == "Live Consumers": _events(service, platform, actor, institution_id, roles)
    elif workspace == "RAG Quality": _rag(service, platform, actor, institution_id, roles)
    elif workspace == "Research Alerts": _alerts(service, platform, actor, institution_id, roles)
    elif workspace == "Scientific Workbench": _scientific(service, platform, actor, institution_id, roles)
    elif workspace == "Media Pipeline": _media(service, platform, actor, institution_id, roles)
    else: _overview(service, actor, institution_id)
