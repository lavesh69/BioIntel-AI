from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

from biointel.connected.free_web_ai import DEFAULT_OLLAMA_MODEL, FreeWebCopilot, free_web_stack_diagnostic
from biointel.connected.providers import PROVIDERS
from biointel.ui.operational_canvas import render_operational_canvas
from biointel.contextual_research_v196.catalog import (
    get_module_research_profile,
    has_relevant_top_websites,
    provider_query_url,
)
from biointel.contextual_research_v196.service import contextual_provider_search

ROOT = Path(__file__).resolve().parents[3]


def _safe_workspace_context() -> str:
    rows: list[str] = []
    labels = {
        "active_project": "Active project",
        "active_dataset": "Active dataset",
        "active_model": "Active model",
        "active_target": "Active target",
    }
    for key, label in labels.items():
        value = st.session_state.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            rows.append(f"{label}: {str(value).strip()[:500]}")
    return "\n".join(rows)


def _provider_names(keys: list[str] | tuple[str, ...]) -> list[str]:
    return [PROVIDERS[key].name for key in keys if key in PROVIDERS]


def _show_evidence(evidence: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
    records: list[dict[str, Any]] = []
    for group in evidence:
        provider = str(group.get("provider", "provider"))
        for row in group.get("records", []) if isinstance(group.get("records"), list) else []:
            if isinstance(row, dict):
                records.append({
                    "provider": PROVIDERS[provider].name if provider in PROVIDERS else provider,
                    "record_id": row.get("record_id", ""),
                    "title": row.get("title", ""),
                    "summary": row.get("summary", ""),
                    "source_url": row.get("source_url", ""),
                })
    if records:
        st.dataframe(
            records,
            width="stretch",
            height=min(420, 100 + len(records) * 35),
            hide_index=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Official source", display_text="Open"),
            },
        )
    else:
        st.info("No normalized evidence records were returned.")



def _direct_provider_label(provider: str, entity_type: str) -> str:
    if provider == "ncbi":
        labels = {
            "literature": "PubMed",
            "variant": "NCBI ClinVar",
            "expression study": "NCBI GEO",
            "sequence": "NCBI Sequence",
            "gene": "NCBI Gene",
            "protein": "NCBI Protein",
        }
        return labels.get(entity_type, "NCBI")
    return PROVIDERS[provider].name if provider in PROVIDERS else provider


def _render_direct_website_access(module_key: str, profile: Any, prefix: str) -> None:
    with st.container(border=True):
        st.markdown(f"#### 🌐 Relevant scientific websites · {profile.title}")
        st.caption(
            "Only official websites relevant to this module are shown. "
            "Enter an optional gene, compound, accession, disease or study term, then open the source directly."
        )
        direct_query = st.text_input(
            "Website search term (optional)",
            key=f"{prefix}_direct_website_query",
            placeholder=profile.query_hint,
            max_chars=2_000,
        )
        providers = [provider for provider in profile.providers if provider in PROVIDERS]
        for row_start in range(0, len(providers), 4):
            row = providers[row_start : row_start + 4]
            columns = st.columns(len(row))
            for index, provider in enumerate(row):
                entity_type = profile.entity_type_for(provider)
                columns[index].link_button(
                    _direct_provider_label(provider, entity_type),
                    provider_query_url(provider, direct_query, entity_type),
                    width="stretch",
                )
        st.caption(
            "Direct links open the official provider in your browser. "
            "Do not search patient identifiers, confidential sequences or proprietary project names on public services."
        )

def render_contextual_online_research(module_key: str, *, expanded: bool = False) -> None:
    """Render top website access and online research only for relevant modules."""
    if not has_relevant_top_websites(module_key):
        return
    profile = get_module_research_profile(module_key)
    prefix = f"step196_online_{module_key}"
    default_model = os.getenv("BIOINTEL_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL

    _render_direct_website_access(module_key, profile, prefix)

    with st.expander(f"🔎 Online Research & Local AI · {profile.title}", expanded=expanded):
        st.caption(
            f"Contextual online support for {profile.research_focus}. "
            "Uses free local Ollama, SearXNG web search and official scientific provider websites."
        )
        quick_cols = st.columns(len(profile.quick_queries))
        for index, quick_query in enumerate(profile.quick_queries):
            if quick_cols[index].button(quick_query, key=f"{prefix}_quick_{index}", width="stretch"):
                st.session_state[f"{prefix}_query"] = quick_query

        query = st.text_input(
            "Scientific query",
            key=f"{prefix}_query",
            placeholder=profile.query_hint,
            max_chars=2_000,
        )
        provider_labels = {key: PROVIDERS[key].name for key in PROVIDERS}
        selected = st.multiselect(
            "Official scientific providers",
            options=list(PROVIDERS),
            default=list(profile.providers),
            format_func=lambda key: provider_labels.get(key, key),
            key=f"{prefix}_providers",
            help="All official scientific providers are available; select any provider for your research query.",
        )



        settings_cols = st.columns(3)
        use_web = settings_cols[0].checkbox(
            "SearXNG web search",
            value=True,
            key=f"{prefix}_use_web",
        )
        use_providers = settings_cols[1].checkbox(
            "Official databases",
            value=True,
            key=f"{prefix}_use_providers",
        )
        include_context = settings_cols[2].checkbox(
            "Include workspace context",
            value=False,
            key=f"{prefix}_include_context",
            help="Includes only active project, dataset, model and target labels; raw files are never sent automatically.",
        )

        with st.popover("Advanced connection settings"):
            model = st.text_input(
                "Ollama model",
                value=default_model,
                key=f"{prefix}_model",
            )
            searxng_url = st.text_input(
                "Private SearXNG URL (optional)",
                value=os.getenv("SEARXNG_URL", ""),
                key=f"{prefix}_searxng_url",
                placeholder="https://your-private-searxng.example",
            )
            if st.button("Test free web stack", key=f"{prefix}_diagnostic"):
                with st.spinner("Testing Ollama and SearXNG…"):
                    report = free_web_stack_diagnostic(ROOT, model=model, searxng_url=searxng_url or None)
                if report.get("ready"):
                    st.success("Ollama model and SearXNG are ready.")
                else:
                    st.warning("One or more free-web components need attention.")
                render_operational_canvas(
                    title="Optional service canvas",
                    subtitle="Local Ollama and optional SearXNG readiness. Missing services never block offline work.",
                    payload=report,
                    stages=("Detect", "Connect", "Verify", "Ready or unavailable"),
                    key=f"{prefix}_service_canvas",
                )

        tab_ai, tab_provider, tab_websites = st.tabs(
            ["Free Web AI Answer", "Official Database Results", "Open Websites"]
        )

        provider_entity_types = {
            provider: profile.entity_type_for(provider)
            for provider in selected
            if provider in PROVIDERS
        }
        workspace_context = _safe_workspace_context() if include_context else ""

        with tab_ai:
            st.caption(
                "Retrieves current web/provider evidence first, then generates a citation-grounded answer locally through Ollama."
            )
            if st.button("Run Free Web AI", key=f"{prefix}_run_ai", type="primary", width="stretch"):
                if not query.strip():
                    st.error("Enter a scientific query first.")
                elif not use_web and not (use_providers and selected):
                    st.error("Enable SearXNG or select at least one official provider.")
                else:
                    try:
                        with st.status("Retrieving evidence and running local AI…", expanded=True) as status:
                            result = FreeWebCopilot(
                                ROOT,
                                model=model,
                                searxng_url=searxng_url or None,
                            ).run(
                                query,
                                allowed_providers=selected,
                                context=workspace_context,
                                use_web_search=use_web,
                                use_scientific_providers=use_providers,
                                provider_entity_types=provider_entity_types,
                            )
                            status.update(label="Contextual online research completed", state="complete")
                        st.session_state[f"{prefix}_ai_result"] = result
                    except Exception as exc:
                        st.error(f"Online research failed safely: {exc}")

            result = st.session_state.get(f"{prefix}_ai_result")
            if result is not None:
                st.markdown(result.answer)
                st.caption(
                    f"Model {result.model} · tool calls {result.tool_calls} · "
                    f"tokens {result.input_tokens}/{result.output_tokens}"
                )
                with st.expander("Retrieved evidence", expanded=False):
                    _show_evidence(list(result.evidence))
                export = {
                    "module_key": module_key,
                    "module_title": profile.title,
                    "query": query,
                    "answer": result.answer,
                    "model": result.model,
                    "mode": result.mode,
                    "evidence": list(result.evidence),
                }
                st.download_button(
                    "Download answer + citations",
                    json.dumps(export, indent=2, default=str).encode("utf-8"),
                    file_name=f"{module_key}_online_research.json",
                    mime="application/json",
                    key=f"{prefix}_download_ai",
                )

        with tab_provider:
            st.caption("Searches official provider APIs directly; Ollama is not required for this tab.")
            if st.button("Search Official Databases", key=f"{prefix}_run_providers", width="stretch"):
                if not query.strip():
                    st.error("Enter a scientific query first.")
                elif not selected:
                    st.error("Select at least one official provider.")
                else:
                    try:
                        with st.spinner("Searching official scientific databases…"):
                            payload = contextual_provider_search(
                                ROOT,
                                query,
                                provider_entity_types=provider_entity_types,
                                limit=5,
                            )
                        st.session_state[f"{prefix}_provider_result"] = payload
                    except Exception as exc:
                        st.error(f"Provider search failed safely: {exc}")

            payload = st.session_state.get(f"{prefix}_provider_result")
            if isinstance(payload, dict):
                records = payload.get("records", [])
                if records:
                    st.dataframe(
                        records,
                        width="stretch",
                        height=min(440, 100 + len(records) * 35),
                        hide_index=True,
                        column_config={
                            "source_url": st.column_config.LinkColumn("Official source", display_text="Open"),
                        },
                    )
                if payload.get("errors"):
                    st.warning(f"{len(payload['errors'])} provider request(s) did not complete.")
                    render_operational_canvas(
                        title="Provider availability canvas",
                        subtitle="Unavailable optional providers are reported clearly; no result is silently invented.",
                        payload=payload["errors"],
                        stages=("Request", "Timeout or response", "Record source state", "Continue safely"),
                        key=f"{prefix}_provider_errors",
                    )
                st.download_button(
                    "Download provider evidence",
                    json.dumps(payload, indent=2, default=str).encode("utf-8"),
                    file_name=f"{module_key}_provider_evidence.json",
                    mime="application/json",
                    key=f"{prefix}_download_provider",
                )

        with tab_websites:
            st.caption(
                "Open the official websites directly. The current query is added to supported website search links."
            )
            keys = selected or list(profile.providers)
            columns = st.columns(min(4, max(1, len(keys))))
            for index, provider in enumerate(keys):
                if provider not in PROVIDERS:
                    continue
                columns[index % len(columns)].link_button(
                    PROVIDERS[provider].name,
                    provider_query_url(provider, query),
                    width="stretch",
                )
            st.info(
                "Public SearXNG searches leave this computer. Do not enter patient identifiers, confidential sequences or proprietary project terms. "
                "Use a private SearXNG instance for sensitive organizational work."
            )
