from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterator
from uuid import uuid4

import pandas as pd
import streamlit as st

from biointel.shiro.core.cancellation import CANCELLATIONS
from biointel.shiro.core.orchestrator import ShiroOrchestrator
from biointel.shiro.exports import conversation_docx, conversation_json, conversation_markdown, conversation_pdf
from biointel.shiro.integrations.demo import DEMO_PROJECT_ID, DEMO_PROJECT_NAME
from biointel.shiro.runtime_config import MODE_LABELS, PROVIDER_PUBLIC_NAMES
from biointel.shiro.voice import synthesize_windows_wav, transcribe_voice
from biointel.ui.product_experience_v8 import module_tiles, render_product_hero
from biointel.ui.frontend_v10 import apply_frontend_v10, empty_state

SUPPORTED_UPLOADS = ["txt", "md", "csv", "tsv", "json", "pdf", "docx", "html", "htm", "fasta", "fa", "fna", "fastq", "fq", "vcf", "bed", "gff", "gtf", "ipynb", "png", "jpg", "jpeg", "webp"]
SOURCE_SCOPES = {
    "All internal evidence": None,
    "BioIntel reports": ["biointel_report"],
    "Module results": ["module_result"],
}


PROMPT_SUGGESTIONS = {
    "Summarize evidence": "Summarize the strongest findings in this project's indexed evidence and cite every claim.",
    "Find limitations": "What limitations, uncertainties, or missing evidence should I review in this project?",
    "Compare results": "Compare the main scientific results in the indexed evidence and preserve all identifiers.",
    "Plan next steps": "Based only on the indexed evidence, propose cautious next analysis steps and cite the supporting sources.",
}

@st.cache_resource
def _service(root_text: str) -> ShiroOrchestrator:
    return ShiroOrchestrator(Path(root_text))


def _stream_text(value: str, cancelled: Callable[[], bool] | None = None) -> Iterator[str]:
    for paragraph in value.split("\n"):
        if cancelled and cancelled():
            yield "\nGeneration cancelled by the user.\n"
            return
        yield paragraph + "\n"


def _cancel_request(request_id: str) -> None:
    CANCELLATIONS.cancel(request_id)


def _project_label(project: object) -> str:
    prefix = "Synthetic demo · " if project.synthetic else ""
    return f"{prefix}{project.name} · {project.project_id}"


def _render_citations(
    service: ShiroOrchestrator,
    project_id: str,
    citations: list[dict[str, object]],
    key_prefix: str = "",
) -> None:
    if not citations:
        return
    st.caption(f"{len(citations)} traceable source citation(s)")
    for idx, citation in enumerate(citations):
        label = f"[{citation['citation_id']}] {citation['source_title']} · {citation['location']}"
        cite_id = citation.get("citation_id", f"c{idx}")
        chunk_id = citation.get("chunk_id", f"chk{idx}")
        prefix = f"{key_prefix}_" if key_prefix else ""
        exp_key = f"shiro_cite_exp_{prefix}{cite_id}_{chunk_id}_{idx}"
        expander = st.expander(label, icon=":material/description:", key=exp_key, on_change="rerun")
        if expander.open:
            with expander:
                badge = "External" if citation.get("external") else "Internal"
                st.markdown(f":blue-badge[{badge}] " + (":orange-badge[Synthetic evidence]" if citation.get("synthetic") else ""))
                st.caption(
                    f"Project: {citation['project_name']} · type: {citation['source_type']} · "
                    f"relevance: {float(citation['relevance_score']):.3f}"
                )
                st.write(citation["excerpt"])
                if st.button(
                    "Open source preview", key=f"shiro_preview_{prefix}{cite_id}_{chunk_id}_{idx}",
                    icon=":material/visibility:",
                ):
                    st.session_state["shiro_preview_source"] = citation["source_id"]
                    st.rerun()


def _render_jobs(service: ShiroOrchestrator, project_id: str) -> None:
    jobs = service.repository.list_jobs(project_id, 10)
    if not jobs:
        st.caption("No ingestion or indexing jobs yet.")
        return
    for job in jobs:
        state = str(job["state"])
        st.caption(f"{job['job_type']} · {state} · {job['job_id'][-8:]}")
        st.progress(float(job["progress"]), text=f"{float(job['progress']) * 100:.0f}%")
        if state in {"queued", "running"}:
            if st.button("Cancel job", key=f"shiro_cancel_{job['job_id']}", icon=":material/cancel:"):
                service.jobs.cancel(project_id, str(job["job_id"]))
                st.rerun()
        if job.get("error"):
            st.error(str(job["error"]))


def _project_message_summary(service: ShiroOrchestrator, project_id: str) -> dict[str, int]:
    summary = Counter()
    for conversation in service.repository.list_conversations(project_id, 50):
        for message in service.repository.list_messages(project_id, str(conversation["conversation_id"])):
            if message["role"] != "assistant":
                continue
            summary["assistant_responses"] += 1
            summary["citations"] += len(message.get("citations", []))
            evidence_status = str(message.get("retrieval", {}).get("evidence_status", "unknown"))
            summary[evidence_status] += 1
    return dict(summary)


def _render_grounding_workflow(
    *,
    source_count: int,
    chunk_count: int,
    grounded_answers: int,
    citation_count: int,
) -> None:
    stages = (
        ("Evidence", ":material/library_books:", source_count, source_count > 0, "source(s) scoped"),
        ("Index", ":material/hub:", chunk_count, chunk_count > 0, "chunk(s) searchable"),
        ("Ground", ":material/psychology:", grounded_answers, grounded_answers > 0, "answer(s) grounded"),
        ("Cite", ":material/format_quote:", citation_count, citation_count > 0, "citation(s) traced"),
    )
    st.subheader("Grounding workflow", anchor=False)
    st.caption("Every stage below is calculated from this project's persisted evidence and conversations.")
    columns = st.columns(4, gap="small")
    for column, (label, icon, value, ready, detail) in zip(columns, stages):
        with column.container(border=True, height="stretch"):
            st.markdown(f"### {icon} {label}")
            st.badge(
                "Ready" if ready else "Waiting",
                icon=":material/check_circle:" if ready else ":material/schedule:",
                color="green" if ready else "gray",
            )
            st.metric(detail, value)
            st.progress(1.0 if ready else 0.0, text="Persisted" if ready else "No recorded state")


def _render_evidence_graphics(
    service: ShiroOrchestrator,
    active_project: object,
    status: dict[str, object],
) -> None:
    project_id = active_project.project_id
    sources = service.repository.list_sources(project_id)
    message_summary = _project_message_summary(service, project_id)
    source_types = Counter(
        (source.source_type or "uploaded_evidence").replace("_", " ").title()
        for source in sources
    )
    with st.container(border=True):
        st.subheader("Project evidence atlas", anchor=False)
        st.caption("A live visual template built only from sources stored inside the active project boundary.")
        distribution, integrity = st.columns([1.35, 1], gap="medium")
        with distribution:
            st.markdown("**Evidence composition**")
            if source_types:
                frame = pd.DataFrame(
                    {
                        "Evidence type": list(source_types.keys()),
                        "Indexed sources": list(source_types.values()),
                    }
                ).sort_values("Indexed sources", ascending=True)
                st.bar_chart(
                    frame,
                    x="Evidence type",
                    y="Indexed sources",
                    horizontal=True,
                    color="#36c4b3",
                    height=230,
                )
            else:
                with st.container(border=True, horizontal_alignment="center"):
                    st.markdown(":material/library_add:")
                    st.markdown("**No evidence composition yet**")
                    st.caption("Attach a supported project source to activate this graphic.")
        with integrity:
            st.markdown("**Scope and integrity flags**")
            total = len(sources)
            internal = sum(bool(source.internal) and not bool(source.external) for source in sources)
            confidential = sum(bool(source.confidential) for source in sources)
            warning_free = sum(not source.warnings for source in sources)
            synthetic = sum(bool(source.synthetic) for source in sources)
            ratios = (
                ("Internal scope", internal),
                ("Confidential flag", confidential),
                ("Warning-free extraction", warning_free),
            )
            for label, value in ratios:
                ratio = value / total if total else 0.0
                st.progress(ratio, text=f"{label} - {value}/{total}")
            if synthetic:
                st.warning(f"{synthetic} synthetic evidence source(s) are explicitly labelled.", icon=":material/science:")
            elif total:
                st.caption("No synthetic evidence is present in this project.")
            else:
                st.caption("Integrity ratios activate after the first source is indexed.")
        if sources:
            timeline_rows = []
            for source in sources:
                parsed = pd.to_datetime(source.uploaded_at, errors="coerce", utc=True)
                if not pd.isna(parsed):
                    timeline_rows.append(parsed.date())
            if timeline_rows:
                timeline = (
                    pd.Series(timeline_rows, name="Date")
                    .value_counts()
                    .sort_index()
                    .rename_axis("Date")
                    .reset_index(name="Sources indexed")
                )
                if len(timeline) > 1:
                    st.markdown("**Index activity**")
                    st.area_chart(timeline, x="Date", y="Sources indexed", color="#7c83ff", height=170)
                else:
                    st.caption(f"Index activity - {int(timeline['Sources indexed'].sum())} source(s) recorded on {timeline.iloc[0]['Date']}.")
    _render_grounding_workflow(
        source_count=int(status["sources"]),
        chunk_count=int(status["chunks"]),
        grounded_answers=int(message_summary.get("grounded", 0)),
        citation_count=int(message_summary.get("citations", 0)),
    )


def _render_conversation_graphics(messages: list[dict[str, object]]) -> None:
    assistant = [message for message in messages if message["role"] == "assistant"]
    if not assistant:
        return
    statuses = Counter(
        str(message.get("retrieval", {}).get("evidence_status", "unknown")).replace("_", " ").title()
        for message in assistant
    )
    citations = [len(message.get("citations", [])) for message in assistant]
    grounded = sum(
        str(message.get("retrieval", {}).get("evidence_status", "")) == "grounded"
        for message in assistant
    )
    with st.expander("Conversation grounding graphics", icon=":material/analytics:"):
        metric_row = st.container(horizontal=True)
        with metric_row:
            st.metric("Assistant responses", len(assistant), border=True)
            st.metric("Grounded responses", grounded, border=True)
            st.metric("Traceable citations", sum(citations), border=True)
        chart, coverage = st.columns([1.3, 1], gap="medium")
        with chart:
            status_frame = pd.DataFrame(
                {"Evidence status": list(statuses.keys()), "Responses": list(statuses.values())}
            ).sort_values("Responses", ascending=True)
            st.bar_chart(
                status_frame,
                x="Evidence status",
                y="Responses",
                horizontal=True,
                color="#7c83ff",
                height=210,
            )
        with coverage.container(border=True, height="stretch"):
            ratio = grounded / len(assistant) if assistant else 0.0
            st.markdown("**Grounding coverage**")
            st.progress(ratio, text=f"{grounded}/{len(assistant)} responses grounded")
            cited = sum(value > 0 for value in citations)
            st.progress(cited / len(assistant), text=f"{cited}/{len(assistant)} responses cited")
            if grounded < len(assistant):
                st.caption("Greeting, safety-blocked, or insufficient-evidence responses are retained honestly.")
            else:
                st.caption("Every assistant response in this conversation is grounded in indexed evidence.")

def _set_suggested_prompt(value: str) -> None:
    st.session_state["shiro_composer"] = value


def _render_premium_hero(
    service: ShiroOrchestrator,
    active_project: object,
    status: dict[str, object],
    provider: str,
    *,
    external_enabled: bool,
) -> None:
    conversations = service.repository.list_conversations(active_project.project_id)
    jobs = service.repository.list_jobs(active_project.project_id, 50)
    active_jobs = sum(str(item["state"]) in {"queued", "running"} for item in jobs)
    ready = int(status["sources"]) > 0
    render_product_hero(
        "shiro",
        "Shiro AI",
        "Project-isolated biomedical intelligence grounded in indexed evidence, traceable citations and explicit uncertainty.",
        chips=(
            "Evidence ready" if ready else "Evidence required",
            f"Mode: {MODE_LABELS.get(provider, provider)}",
            "Project isolated",
            "Cloud approved for this request" if external_enabled else "Cloud blocked",
        ),
    )
    module_tiles((
        ("GROUND", "Evidence atlas", "Index project files, inspect source quality and preserve project boundaries."),
        ("RETRIEVE", "Citation engine", "Retrieve bounded evidence chunks with traceable source locations."),
        ("REASON", "Scientific assistant", "Generate cautious project-aware answers with explicit uncertainty."),
        ("VERIFY", "Review workspace", "Open sources, inspect citations and export evidence-backed conversations."),
    ))
    st.caption(f"Active project · {active_project.name} · {active_project.project_id}")
    with st.container(horizontal=True):
        st.metric("Indexed sources", int(status["sources"]), border=True)
        st.metric("Evidence chunks", int(status["chunks"]), border=True)
        st.metric("Conversations", len(conversations), border=True)
        st.metric("Active index jobs", active_jobs, border=True)


def _render_provider_readiness(service: ShiroOrchestrator) -> None:
    st.caption("Readiness is based on real configuration. Cloud connections are tested only when you explicitly request a test.")
    columns = st.columns(4, gap="small")
    for column, item in zip(columns, service.providers()):
        with column.container(border=True, height="stretch"):
            st.subheader(item.public_name or PROVIDER_PUBLIC_NAMES.get(item.name, "Shiro Intelligence"), anchor=False)
            st.badge(
                "Configured" if item.available else "Setup required",
                icon=":material/check_circle:" if item.available else ":material/settings:",
                color="green" if item.available else "gray",
            )
            st.caption(item.model or "No model configured")
            st.write(item.detail)
            if st.button("Test", key=f"shiro_health_{item.name}", disabled=not item.available, icon=":material/health_and_safety:"):
                with st.spinner("Checking provider health…"):
                    result = service.provider_health(item.name)
                (st.success if result.get("healthy") else st.error)(str(result.get("detail") or result))
            st.caption("Cloud · consent required" if item.external else "Runs locally")


def _render_provider_settings(service: ShiroOrchestrator) -> None:
    with st.expander("Shiro AI setup", icon=":material/tune:", on_change="rerun"):
        config = service.runtime
        st.caption("Normal chat surfaces use BioIntel Shiro names. Provider identities and credentials remain inside this setup boundary.")
        local_model = st.text_input("Local chat model", value=config.local_model, key="shiro_cfg_local")
        vision_model = st.text_input("Local vision model", value=config.local_vision_model, key="shiro_cfg_vision")
        reasoning_model = st.text_input("Local reasoning model", value=config.local_reasoning_model, key="shiro_cfg_reasoning")
        online_model = st.text_input("Online enhancement model", value=config.gemini_model, key="shiro_cfg_online")
        backup_model = st.text_input("Backup free-model router", value=config.openrouter_model, key="shiro_cfg_backup")
        allow_fallback = st.toggle("Allow cloud fallback in Auto mode", value=config.allow_cloud_fallback, key="shiro_cfg_fallback", help="A cloud request still requires the per-request consent toggle.")
        saved_consent = st.toggle("Remember that cloud services may process submitted content", value=config.cloud_consent_saved, key="shiro_cfg_consent")
        eligibility = st.toggle(
            "I am authorized and eligible to use the configured online services",
            value=config.cloud_eligibility_confirmed, key="shiro_cfg_eligibility",
            help="Online services have age, region, organization and acceptable-use terms. The current Gemini developer terms require an adult user and professional or business use.",
        )
        online_key = st.text_input("Shiro Online Intelligence API key", type="password", key="shiro_cfg_online_key", placeholder="Leave blank to keep existing key")
        backup_key = st.text_input("Shiro Backup Intelligence API key", type="password", key="shiro_cfg_backup_key", placeholder="Leave blank to keep existing key")
        limits = st.columns(3)
        history_limit = limits[0].number_input("History messages", min_value=2, max_value=100, value=int(config.max_history_messages))
        output_limit = limits[1].number_input("Max output tokens", min_value=128, max_value=8192, value=int(config.max_output_tokens), step=128)
        temperature = limits[2].number_input("Creativity", min_value=0.0, max_value=1.5, value=float(config.temperature), step=0.1)
        if st.button("Save Shiro AI setup", icon=":material/save:", type="primary"):
            config.local_model = local_model.strip() or "qwen3:4b"
            config.local_vision_model = vision_model.strip() or "gemma3:4b"
            config.local_reasoning_model = reasoning_model.strip() or "deepseek-r1:8b"
            config.gemini_model = online_model.strip() or "gemini-3.1-flash-lite"
            config.openrouter_model = backup_model.strip() or "openrouter/free"
            config.allow_cloud_fallback = bool(allow_fallback)
            config.cloud_consent_saved = bool(saved_consent)
            config.cloud_eligibility_confirmed = bool(eligibility)
            config.max_history_messages = int(history_limit)
            config.max_output_tokens = int(output_limit)
            config.temperature = float(temperature)
            config.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
            config.save(service.settings.data_dir)
            if online_key or backup_key:
                values = {}
                if online_key:
                    values["gemini_api_key"] = online_key
                if backup_key:
                    values["openrouter_api_key"] = backup_key
                service.secrets.update(**values)
            _service.clear()
            st.success("Shiro AI setup saved securely on this computer.")
            st.rerun()


def _render_actions(actions: list[dict[str, object]], key_prefix: str) -> None:
    if not actions:
        return
    st.caption("BioIntel actions · user approval required")
    with st.container(horizontal=True):
        for index, action in enumerate(actions[:3]):
            if st.button(str(action.get("label", "Open module")), key=f"{key_prefix}_action_{index}", icon=":material/open_in_new:"):
                page = str(action.get("page", ""))
                if page:
                    st.switch_page(page)


def _render_exports(project_id: str, messages: list[dict[str, object]]) -> None:
    if not messages:
        return
    title = f"Shiro AI · {project_id}"
    markdown = conversation_markdown(title, messages).encode("utf-8")
    with st.popover("Export conversation", icon=":material/download:"):
        st.download_button("JSON", conversation_json(messages), file_name=f"shiro-{project_id}.json", mime="application/json")
        st.download_button("Markdown", markdown, file_name=f"shiro-{project_id}.md", mime="text/markdown")
        try:
            st.download_button("DOCX", conversation_docx(title, messages), file_name=f"shiro-{project_id}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            st.download_button("PDF", conversation_pdf(title, messages), file_name=f"shiro-{project_id}.pdf", mime="application/pdf")
        except Exception as exc:
            st.warning(f"Document export is unavailable: {exc}")


def _render_prompt_suggestions() -> None:
    with st.container(border=True):
        st.subheader("Start with project evidence", anchor=False)
        st.caption("Choose a grounded question or write your own in the composer.")
        with st.container(horizontal=True):
            for label, value in PROMPT_SUGGESTIONS.items():
                st.button(
                    label,
                    key=f"shiro_suggestion_{label.casefold().replace(' ', '_')}",
                    icon=":material/auto_awesome:",
                    on_click=_set_suggested_prompt,
                    args=(value,),
                )

def render_page(root: str | Path) -> None:
    apply_frontend_v10("shiro")
    root_path = Path(root).resolve()
    service = _service(str(root_path))
    projects = service.projects()
    labels = {_project_label(project): project for project in projects}
    if not labels:
        empty_state("No BioIntel project is available", "Shiro needs a project-scoped evidence workspace before a conversation can begin.", icon="✦", action_hint="Create or restore a BioIntel project, then reopen Shiro AI.")
        return
    if st.session_state.get("shiro_project_label") not in labels:
        st.session_state["shiro_project_label"] = next(iter(labels))
    st.session_state.setdefault("shiro_conversation_id", None)
    st.session_state.setdefault("shiro_preview_source", None)


    with st.sidebar:
        st.subheader("Shiro workspace")
        project_label = st.selectbox("Active project", list(labels), key="shiro_project_label")
        active_project = labels[project_label]
        if st.session_state.get("shiro_last_project") != active_project.project_id:
            st.session_state["shiro_last_project"] = active_project.project_id
            st.session_state["shiro_conversation_id"] = None
            st.session_state["shiro_preview_source"] = None
        language = st.selectbox("Response language", ["auto", "English", "Hindi", "Hinglish"], key="shiro_language")
        source_scope = st.selectbox("Evidence scope", list(SOURCE_SCOPES), key="shiro_source_scope")
        top_k = st.slider("Evidence results", 1, 12, service.settings.retrieval_top_k, key="shiro_top_k")
        rerank = st.toggle("Local reranking", value=service.settings.reranker_enabled, key="shiro_rerank")
        mode_by_label = {label: mode for mode, label in MODE_LABELS.items()}
        current_mode_label = MODE_LABELS.get(service.runtime.mode, MODE_LABELS["auto"])
        selected_mode_label = st.selectbox("Intelligence mode", list(mode_by_label), index=list(mode_by_label).index(current_mode_label), key="shiro_mode", help="Auto is local-first. Online Enhanced requires an API key and explicit consent.")
        provider = mode_by_label[selected_mode_label]
        cloud_capable = provider in {"auto", "online_enhanced"} and service.runtime.cloud_eligibility_confirmed
        external = st.toggle(
            "Allow cloud processing for this request", value=False, disabled=not cloud_capable, key="shiro_cloud_consent",
            help="When enabled, the current prompt, selected evidence excerpts and attached images may be sent to a configured cloud provider. Provider eligibility must first be confirmed in Shiro AI setup.",
        )
        background_upload = st.toggle(
            "Background attachment indexing", value=False, key="shiro_background_upload",
            help="Queues attachment ingestion and keeps the UI responsive. Ask after the job completes.",
        )
        status = service.repository.index_status(active_project.project_id)
        st.caption(f"Persistent index · {status['sources']} sources · {status['chunks']} chunks")
        st.markdown(":green-badge[Local & private] :blue-badge[Project isolated]")
        if active_project.synthetic:
            st.warning("This project contains synthetic demo evidence only.", icon=":material/science:")
        if external:
            st.warning("Cloud processing is approved only for the next submitted request. Unpaid services may retain or review submitted content under their terms; do not send confidential, clinical, personal, or unpublished data.", icon=":material/cloud_upload:")
        elif provider in {"auto", "online_enhanced"} and not service.runtime.cloud_eligibility_confirmed:
            st.caption("Cloud processing is blocked until provider eligibility is confirmed in Shiro AI setup.")
        else:
            st.caption("Cloud processing is blocked. Local project data stays on this computer.")
        _render_provider_settings(service)

        demo_panel = st.expander("Synthetic demo", icon=":material/science:", on_change="rerun")
        if demo_panel.open:
            with demo_panel:
                st.caption("Deterministic, clearly labelled evidence. Never mixed with real data unless you select the demo project.")
                if st.button("Create / restore demo", key="shiro_create_demo", icon=":material/add_circle:"):
                    service.create_demo()
                    st.session_state["shiro_project_label"] = f"Synthetic demo · {DEMO_PROJECT_NAME} · {DEMO_PROJECT_ID}"
                    st.rerun()
                if st.button("Reset demo", key="shiro_reset_demo", icon=":material/restart_alt:"):
                    service.reset_demo()
                    st.session_state.pop("shiro_project_label", None)
                    st.rerun()

        jobs_panel = st.expander("Index & jobs", icon=":material/work_history:", on_change="rerun")
        if jobs_panel.open:
            with jobs_panel:
                with st.container(horizontal=True):
                    if st.button("Rebuild index", key="shiro_rebuild", icon=":material/rebuild:"):
                        service.submit_index_rebuild(active_project.project_id)
                        st.rerun()
                    st.button("Refresh", key="shiro_refresh_jobs", icon=":material/refresh:")
                _render_jobs(service, active_project.project_id)

        st.subheader("Conversations")
        conversations = service.repository.list_conversations(active_project.project_id)
        if conversations:
            conversation_labels = {item["title"] + " · " + item["conversation_id"][-6:]: item["conversation_id"] for item in conversations}
            current = st.session_state.get("shiro_conversation_id")
            default_index = list(conversation_labels.values()).index(current) if current in conversation_labels.values() else 0
            selected = st.selectbox("History", list(conversation_labels), index=default_index, label_visibility="collapsed")
            st.session_state["shiro_conversation_id"] = conversation_labels[selected]
        else:
            st.caption("No saved conversations in this project.")
        with st.container(horizontal=True):
            if st.button("New", icon=":material/add:"):
                st.session_state["shiro_conversation_id"] = service.repository.create_conversation(active_project.project_id)
                st.rerun()
            if st.session_state.get("shiro_conversation_id") and st.button("Clear", icon=":material/clear_all:"):
                service.repository.clear_conversation(active_project.project_id, st.session_state["shiro_conversation_id"])
                st.rerun()
            if st.session_state.get("shiro_conversation_id") and st.button("Delete", icon=":material/delete:"):
                service.repository.delete_conversation(active_project.project_id, st.session_state["shiro_conversation_id"])
                st.session_state["shiro_conversation_id"] = None
                st.rerun()
        if conversations and st.session_state.get("shiro_conversation_id"):
            rename_panel = st.expander("Rename conversation", on_change="rerun")
            if rename_panel.open:
                current_item = next((item for item in conversations if item["conversation_id"] == st.session_state["shiro_conversation_id"]), conversations[0])
                with rename_panel:
                    title = st.text_input("Conversation title", value=str(current_item["title"]), max_chars=160)
                    if st.button("Save title", key="shiro_save_title"):
                        service.repository.rename_conversation(active_project.project_id, st.session_state["shiro_conversation_id"], title)
                        st.rerun()

    active_project = labels[st.session_state["shiro_project_label"]]
    status = service.repository.index_status(active_project.project_id)
    _render_premium_hero(service, active_project, status, provider, external_enabled=external)
    with st.expander("Assistant and provider readiness", icon=":material/settings_suggest:"):
        _render_provider_readiness(service)
    _render_evidence_graphics(service, active_project, status)

    if status["sources"] == 0:
        with st.container(border=True):
            copy, readiness = st.columns([1.7, 1], vertical_alignment="center")
            with copy:
                st.subheader("Build the project evidence base", anchor=False)
                st.write("Attach a report, table, document, notebook, or genomic summary in the composer below. Shiro validates, hashes, persists, indexes, retrieves, and cites the real source.")
                st.caption("FASTA/FASTQ are summarized. Large models are not downloaded automatically.")
            with readiness:
                st.badge("Step 1 · add evidence", icon=":material/library_add:", color="orange")
                st.caption("Step 2 · ask a grounded question")
                st.caption("Step 3 · inspect citations and source preview")

    source_panel = st.expander("Evidence source manager", icon=":material/folder_managed:", on_change="rerun")
    if source_panel.open:
        with source_panel:
            sources = service.repository.list_sources(active_project.project_id)
            if not sources:
                st.caption("No evidence sources in this project.")
            else:
                source_labels = {
                    f"{item.filename} · {item.source_type} · {item.source_id[-8:]}": item for item in sources
                }
                selected_source_label = st.selectbox("Managed source", list(source_labels), key="shiro_managed_source")
                selected_source = source_labels[selected_source_label]
                flags = []
                if selected_source.synthetic:
                    flags.append("Synthetic")
                if selected_source.external:
                    flags.append("External")
                if selected_source.confidential:
                    flags.append("Confidential")
                st.caption(f"{selected_source.byte_size:,} bytes · SHA-256 {selected_source.sha256[:16]}… · {' · '.join(flags) or 'Internal'}")
                if st.button("Delete selected source", key="shiro_delete_source", icon=":material/delete_forever:"):
                    service.ingestion.delete_source(active_project.project_id, selected_source.source_id)
                    if st.session_state.get("shiro_preview_source") == selected_source.source_id:
                        st.session_state["shiro_preview_source"] = None
                    st.rerun()

    conversation_id = st.session_state.get("shiro_conversation_id")
    messages = service.repository.list_messages(active_project.project_id, conversation_id) if conversation_id else []
    if not messages and int(status["sources"]):
        _render_prompt_suggestions()
    _render_conversation_graphics(messages)
    for idx, message in enumerate(messages):
        with st.chat_message(message["role"], avatar=":material/science:" if message["role"] == "assistant" else None):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                msg_key = message.get("message_id", str(idx))
                with st.popover("Copy answer", icon=":material/content_copy:", key=f"shiro_copy_{msg_key}_{idx}"):
                    st.code(message["content"], language=None)
                _render_citations(service, active_project.project_id, message["citations"], key_prefix=f"m_{msg_key}_{idx}")
                _render_actions(list(message.get("retrieval", {}).get("actions", [])), f"m_{msg_key}_{idx}")
                public_provider = PROVIDER_PUBLIC_NAMES.get(str(message.get("provider")), "Shiro Intelligence")
                st.caption(f"{public_provider} · {message['model']} · {message['status']}")

    preview_source = st.session_state.get("shiro_preview_source")
    if preview_source:
        try:
            preview = service.source_preview(active_project.project_id, preview_source)
            with st.container(border=True):
                st.subheader(f":material/visibility: Source preview · {preview['source']['filename']}")
                source = preview["source"]
                st.caption(f"{source['source_type']} · SHA-256 {source['sha256'][:16]}… · uploaded {source['uploaded_at']}")
                if source.get("synthetic"):
                    st.warning("Synthetic demo evidence — not real patient or research data.", icon=":material/science:")
                for chunk in preview["chunks"][:8]:
                    st.caption(f"{chunk['location']} · {chunk['section']}")
                    st.write(chunk["text"])
                managed = service.repository.get_source(active_project.project_id, preview_source)
                managed_path = Path(managed.file_path)
                with st.container(horizontal=True):
                    if managed_path.is_file():
                        st.download_button(
                            "Open / download original", managed_path.read_bytes(), file_name=managed.filename,
                            mime=managed.mime_type, icon=":material/download:",
                        )
                    if st.button("Close preview", icon=":material/close:"):
                        st.session_state["shiro_preview_source"] = None
                        st.rerun()
        except Exception as exc:
            st.error(str(exc), icon=":material/error:")

    last_user = next((message["content"] for message in reversed(messages) if message["role"] == "user"), "")
    with st.container(horizontal=True):
        if last_user and st.button("Regenerate last answer", icon=":material/refresh:"):
            try:
                result = service.chat(
                    active_project.project_id, last_user, conversation_id=conversation_id,
                    response_language=language, top_k=top_k, provider=provider,
                    external_requested=external, cloud_consent=external, rerank=rerank,
                    source_types=SOURCE_SCOPES[source_scope],
                )
                with st.chat_message("assistant", avatar=":material/science:"):
                    st.write_stream(_stream_text(result.answer))
                    _render_citations(service, active_project.project_id, [item.to_dict() for item in result.citations], key_prefix="regen")
            except Exception as exc:
                st.error(str(exc), icon=":material/error:")
        if messages:
            _render_exports(active_project.project_id, messages)
        last_assistant = next((message["content"] for message in reversed(messages) if message["role"] == "assistant"), "")
        if last_assistant and st.button("Continue response", icon=":material/arrow_forward:"):
            try:
                result = service.chat(
                    active_project.project_id, "Continue your previous answer from where it stopped. Do not repeat completed sections.", conversation_id=conversation_id,
                    response_language=language, top_k=top_k, provider=provider, external_requested=external, cloud_consent=external, rerank=rerank, source_types=SOURCE_SCOPES[source_scope],
                )
                with st.chat_message("assistant", avatar=":material/science:"):
                    st.write_stream(_stream_text(result.answer))
                    _render_actions(list(result.actions), "continue")
            except Exception as exc:
                st.error(str(exc), icon=":material/error:")

    with st.expander("Voice conversation", icon=":material/mic:"):
        if hasattr(st, "audio_input"):
            voice = st.audio_input("Record a question")
            if voice is not None and st.button("Transcribe locally", icon=":material/transcribe:"):
                try:
                    with st.spinner("Transcribing on this computer…"):
                        transcript = transcribe_voice(voice.getvalue(), root_path, service.settings.data_dir, language=language)
                    st.session_state["shiro_composer"] = str(transcript["text"])
                    st.success("Voice question added to the composer.")
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.caption("Voice recording requires the current BioIntel desktop runtime.")
        last_answer_for_voice = next((message["content"] for message in reversed(messages) if message["role"] == "assistant"), "")
        if last_answer_for_voice and st.button("Create local spoken answer", icon=":material/volume_up:"):
            try:
                st.audio(synthesize_windows_wav(last_answer_for_voice, service.settings.data_dir), format="audio/wav")
            except Exception as exc:
                st.warning(str(exc))

    prompt = st.chat_input(
        "Ask Shiro anything or attach project evidence",
        accept_file="multiple", file_type=SUPPORTED_UPLOADS, key="shiro_composer",
    )
    if prompt:
        upload_results = []
        attachment_source_ids = []
        queued_jobs = []
        for uploaded in prompt.files:
            try:
                if background_upload:
                    queued = service.submit_ingestion(
                        active_project.project_id, uploaded.getvalue(), uploaded.name,
                        project_name=active_project.name,
                    )
                    queued_jobs.append(queued)
                else:
                    with st.status(f"Indexing {uploaded.name}", expanded=True) as ingestion_status:
                        ingestion_status.write("Validating signature, extracting sections, neutralizing document instructions, and building the project index.")
                        result = service.ingest(
                            active_project.project_id, uploaded.getvalue(), uploaded.name,
                            project_name=active_project.name,
                        )
                        upload_results.append(result)
                        attachment_source_ids.append(result.source.source_id)
                        ingestion_status.update(label=f"{uploaded.name}: {result.chunks_indexed} chunks indexed", state="complete")
                        for warning in result.source.warnings:
                            st.warning(warning, icon=":material/warning:")
            except Exception as exc:
                st.error(f"{uploaded.name}: {exc}", icon=":material/error:")
        if queued_jobs:
            st.info(f"Queued {len(queued_jobs)} background ingestion job(s). Track progress under Index & jobs before asking about the new files.", icon=":material/work_history:")
        text = prompt.text.strip()
        if text:
            if conversation_id is None:
                conversation_id = service.repository.create_conversation(active_project.project_id, text[:80], language)
                st.session_state["shiro_conversation_id"] = conversation_id
            with st.chat_message("user"):
                st.markdown(text)
            with st.chat_message("assistant", avatar=":material/science:"):
                request_id = "ui-" + uuid4().hex
                event = CANCELLATIONS.register(request_id)
                st.button(
                    "Stop generation", key=f"shiro_stop_{request_id}", icon=":material/stop_circle:",
                    on_click=_cancel_request, args=(request_id,),
                    help="Cancels the active local response before the next generation boundary.",
                )
                try:
                    result = service.chat(
                        active_project.project_id, text, conversation_id=conversation_id,
                        response_language=language, top_k=top_k, provider=provider,
                        external_requested=external, cloud_consent=external, attachment_source_ids=attachment_source_ids, rerank=rerank,
                        source_types=SOURCE_SCOPES[source_scope], cancelled=event.is_set,
                        request_id=request_id,
                    )
                    st.write_stream(_stream_text(result.answer, event.is_set))
                    _render_citations(service, active_project.project_id, [item.to_dict() for item in result.citations], key_prefix="stream")
                    _render_actions(list(result.actions), "stream")
                    if result.general_knowledge:
                        st.info("This response includes general model knowledge and is not a project-specific finding unless supported by the citations shown above.", icon=":material/info:")
                except Exception as exc:
                    st.error(str(exc), icon=":material/error:")
                finally:
                    CANCELLATIONS.release(request_id)
        elif upload_results:
            st.success(f"Indexed {len(upload_results)} evidence file(s). Ask a question to retrieve them with citations.", icon=":material/check_circle:")