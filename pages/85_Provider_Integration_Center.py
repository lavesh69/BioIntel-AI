from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.connected.config import public_connection_status  # noqa: E402
from biointel.connected.diagnostics import test_openai_connection  # noqa: E402
from biointel.connected.free_web_ai import free_web_stack_diagnostic  # noqa: E402
from biointel.connected.providers import (  # noqa: E402
    PROVIDERS,
    ConnectedProviderService,
    provider_rows,
)
from biointel.connected.registry import (  # noqa: E402
    latest_health_by_provider,
    recent_health_checks,
    recent_queries,
    registry_summary,
)
from biointel.integrations.cache import ExternalResponseCache  # noqa: E402
from biointel.internet.connectivity import internet_configuration  # noqa: E402
from biointel.ui.components import smart_dataframe, smart_json  # noqa: E402
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import indeterminate_loader

REGISTRY = ROOT / "reports" / "connected_sources.sqlite3"
CACHE = ROOT / "cache" / "connected"

st.set_page_config(page_title="Provider Integration Center · BioIntel AI", page_icon="🔌", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("provider_integration", key_prefix="step116_85_Provider_Integration_Center_provider_integration_1", expanded=False)

hero(
    "Provider Integration Center",
    "Configure and test free Ollama + SearXNG web AI, optional OpenAI and approved biotechnology provider connections.",
    eyebrow="Professional connection diagnostics and recovery",
    chips=[
        "Two-step Windows setup",
        "Free local Ollama",
        "SearXNG web search",
        "OpenAI key test",
        "11 live provider probes",
        "Typed failures",
        "Auditable provenance",
    ],
)

settings = public_connection_status()
summary = registry_summary(REGISTRY)
cache = ExternalResponseCache(CACHE)
metrics = st.columns(8)
metrics[0].metric("Free AI", settings["ollama_model"])
metrics[1].metric("OpenAI", "Configured" if settings["openai_configured"] else "Optional")
metrics[2].metric("Providers", len(PROVIDERS))
metrics[3].metric("Logged queries", summary["queries"])
metrics[4].metric("Records", summary["records"])
metrics[5].metric("Health checks", summary["health_checks"])
metrics[6].metric("Cache entries", len(cache.list_entries()))
metrics[7].metric("Cache size", f"{cache.total_size_bytes() / 1024 / 1024:.2f} MB")

badge("● Free Local + Web mode requires no paid AI API key", "success")
if settings["openai_configured"]:
    badge("● Optional OpenAI API key is configured", "info")

setup_tab, free_tab, openai_tab, health_tab, history_tab, security_tab = st.tabs(
    ["Setup", "Free Web AI", "OpenAI test", "Provider health", "History", "Security & operations"]
)

with setup_tab:
    section_title("Recommended Windows setup", "⚙")
    st.markdown(
        "The normal two-step flow now includes the free web-AI setup:\n\n"
        "1. Run **`INSTALL_WINDOWS.bat`**. It verifies BioIntel, attempts a user-scope Ollama installation and downloads the lightweight default model once.\n"
        "2. Run **`RUN_BOTH_WINDOWS.bat`**.\n\n"
        "No OpenAI or Gemini key is required for **Free Local + Web** mode. SearXNG uses a private URL when configured, otherwise BioIntel discovers a healthy HTTPS public instance and keeps official scientific providers as a separate fallback."
    )
    insight_callout(
        "Privacy boundary",
        "Ollama generation stays on 127.0.0.1. Public SearXNG queries leave the computer, so do not submit patient identifiers or confidential project terms. Configure a private SearXNG URL for sensitive organizational work.",
        "warning",
    )
    section_title("Non-secret configuration", "▤")
    config_frame = pd.DataFrame(
        [
            ("BIOINTEL_OLLAMA_MODEL", settings["ollama_model"], "Free local AI model"),
            ("OLLAMA_BASE_URL", settings["ollama_base_url"], "Loopback-only Ollama API"),
            (
                "SEARXNG_URL",
                settings["searxng_url"] or "Automatic discovery",
                "Private SearXNG endpoint or automatic healthy-instance selection",
            ),
            (
                "OPENAI_API_KEY",
                "Configured" if settings["openai_configured"] else "Missing",
                "OpenAI authentication",
            ),
            ("OPENAI_MODEL", settings["openai_model"], "Model used for Copilot runs"),
            ("OPENAI_BASE_URL", settings["openai_base_url"], "OpenAI API base URL"),
            (
                "OPENAI_PROJECT",
                "Configured" if settings["openai_project_configured"] else "Optional / missing",
                "Project-scoped API routing",
            ),
            (
                "OPENAI_ORGANIZATION",
                "Configured"
                if settings["openai_organization_configured"]
                else "Optional / missing",
                "Organization routing",
            ),
            (
                "OPENAI_STORE_RESPONSES",
                settings["openai_store_responses"],
                "Whether OpenAI response storage is requested",
            ),
            (
                "NCBI_API_KEY",
                "Configured" if settings["ncbi_api_key_configured"] else "Optional / missing",
                "Higher supported NCBI request rate",
            ),
            (
                "NCBI_EMAIL",
                "Configured" if settings["ncbi_email_configured"] else "Recommended / missing",
                "NCBI contact identity",
            ),
            ("NCBI_TOOL", settings["ncbi_tool"], "NCBI client identifier"),
            (
                "STRING_CALLER_IDENTITY",
                settings["string_caller_identity"],
                "STRING API caller identity",
            ),
            ("BIOINTEL_CONNECTED_TIMEOUT", settings["timeout_seconds"], "Read timeout"),
            (
                "BIOINTEL_CONNECTED_CONNECT_TIMEOUT",
                settings["connect_timeout_seconds"],
                "Connection timeout",
            ),
            ("BIOINTEL_CONNECTED_RETRIES", settings["retries"], "Bounded retry count"),
            ("BIOINTEL_CONNECTED_CACHE_TTL", settings["cache_ttl_seconds"], "Fresh-cache lifetime"),
        ],
        columns=["Variable", "Status/value", "Purpose"],
    )
    smart_dataframe(config_frame, height=500)
    section_title("Provider catalogue", "🌐")
    smart_dataframe(
        pd.DataFrame(provider_rows()),
        height=500,
        columns={
            "base_url": st.column_config.LinkColumn("Official API", display_text="Open"),
            "documentation_url": st.column_config.LinkColumn("Documentation", display_text="Docs"),
        },
    )


with free_tab:
    section_title("Validate free Ollama + SearXNG connectivity", "🌐")
    free_model = st.text_input(
        "Ollama model", value=settings["ollama_model"], key="integration_free_ollama_model"
    )
    private_searxng = st.text_input(
        "Private SearXNG URL (optional)",
        value=settings["searxng_url"],
        placeholder="Leave blank for automatic healthy-instance discovery",
        key="integration_free_searxng_url",
    )
    st.caption(
        "Ollama is tested only on http://127.0.0.1:11434. Public SearXNG instances may rate-limit; a private instance is recommended for repeatable or sensitive work."
    )
    if st.button("Run Free Web AI connection test", type="primary"):
        with indeterminate_loader("Testing local Ollama, selected model and SearXNG…"):
            st.session_state["step195_free_web_diagnostic"] = free_web_stack_diagnostic(
                ROOT, model=free_model, searxng_url=private_searxng or None
            )
    free_diagnostic = st.session_state.get("step195_free_web_diagnostic")
    if free_diagnostic:
        cols = st.columns(5)
        ollama = free_diagnostic.get("ollama", {})
        searxng = free_diagnostic.get("searxng", {})
        cols[0].metric("Overall", "Ready" if free_diagnostic.get("ready") else "Needs setup")
        cols[1].metric("Ollama API", "Connected" if ollama.get("available") else "Unavailable")
        cols[2].metric("Model", "Ready" if ollama.get("model_visible") else "Missing")
        cols[3].metric("SearXNG", "Connected" if searxng.get("available") else "Unavailable")
        cols[4].metric("Web results", searxng.get("records", 0))
        if free_diagnostic.get("ready"):
            st.success("Free Local + Web AI is ready without a paid AI API key.")
        else:
            st.warning(ollama.get("error") or searxng.get("error") or "Complete the reported setup step.")
        smart_json(
            free_diagnostic,
            title="Free Web AI diagnostic",
            download_name="free_web_ai_diagnostic.json",
            key="free_web_ai_diagnostic",
        )

with openai_tab:
    section_title("Validate OpenAI authentication and model access", "🤖")
    environment_key = os.getenv("OPENAI_API_KEY", "").strip()
    session_test_key = st.text_input(
        "Session-only OpenAI key for this test",
        type="password",
        help="Leave blank to use OPENAI_API_KEY from the environment. The value is not stored.",
        key="integration_openai_test_key",
    )
    model = st.text_input(
        "Model to validate", value=settings["openai_model"], key="integration_openai_model"
    )
    active_key = session_test_key.strip() or environment_key
    if st.button("Run OpenAI connection test", type="primary", disabled=not active_key):
        with indeterminate_loader("Checking authentication and model visibility…"):
            st.session_state["step52_openai_diagnostic"] = test_openai_connection(
                ROOT, api_key=active_key, model=model
            )
    diagnostic = st.session_state.get("step52_openai_diagnostic")
    if diagnostic:
        cols = st.columns(4)
        cols[0].metric("Authentication", "Passed" if diagnostic.get("available") else "Failed")
        cols[1].metric("Model visible", "Yes" if diagnostic.get("model_visible") else "No")
        cols[2].metric("Models visible", diagnostic.get("visible_model_count", 0))
        cols[3].metric("Latency", f"{diagnostic.get('latency_ms', 0):.0f} ms")
        if diagnostic.get("available") and diagnostic.get("model_visible"):
            st.success(
                "OpenAI key is valid and the selected model is available to this API project."
            )
        elif diagnostic.get("available"):
            st.warning(
                diagnostic.get("error")
                or "Authentication succeeded but the selected model was not listed."
            )
        else:
            st.error(diagnostic.get("error") or "OpenAI connection failed.")
        smart_json(
            {k: v for k, v in diagnostic.items() if k not in {"error"}},
            title="OpenAI connection diagnostic",
            download_name="openai_connection_diagnostic.json",
            key="openai_connection_diagnostic",
        )
    st.caption("This test lists models and does not run a paid model generation request.")

with health_tab:
    st.caption(
        "Provider probes run only when requested. They use minimal official API queries, respect rate limits and may use cache."
    )
    selected = st.multiselect(
        "Providers to probe",
        options=list(PROVIDERS),
        default=list(PROVIDERS),
        format_func=lambda key: PROVIDERS[key].name,
        key="provider_health_selection",
    )
    if st.button("Run selected live provider checks", type="primary", disabled=not selected):
        rows = []
        progress = st.progress(0.0)
        service = ConnectedProviderService(ROOT, persist_queries=False)
        for index, provider in enumerate(selected, 1):
            rows.append(service.probe(provider))
            progress.progress(index / len(selected))
        st.session_state["connected_provider_health"] = rows
    rows = st.session_state.get("connected_provider_health") or latest_health_by_provider(REGISTRY)
    if rows:
        health = pd.DataFrame(rows)
        smart_dataframe(health, height=500)
        available = int(health["available"].sum()) if "available" in health else 0
        badge(
            f"● {available}/{len(health)} providers connected in the latest checks",
            "success" if available == len(health) else "warning",
        )
        if "error_type" in health:
            failures = health[health["available"].astype(int) == 0]
            if not failures.empty:
                section_title("Troubleshooting", "🧰")
                error_types = set(failures["error_type"].astype(str))
                if error_types & {"dns_error", "connection_error", "network_policy"}:
                    st.info(
                        "DNS/network failure: check internet access, VPN/proxy, antivirus web protection, Windows firewall and whether official API domains are blocked."
                    )
                if "authentication_error" in error_types:
                    st.info(
                        "Authentication failure: verify the API key and account/project permissions."
                    )
                if "rate_limited" in error_types:
                    st.info(
                        "Rate limit: wait and retry. BioIntel respects Retry-After and uses bounded backoff."
                    )
                if "not_found" in error_types:
                    st.info(
                        "Not found: the health accession may be unavailable temporarily or the provider API changed; inspect the error and official documentation."
                    )

with history_tab:
    query_rows = recent_queries(REGISTRY, limit=200)
    health_rows = recent_health_checks(REGISTRY, limit=200)
    st.markdown("#### Connected queries")
    if query_rows:
        smart_dataframe(
            pd.DataFrame(query_rows).drop(columns=["warnings_json"], errors="ignore"), height=430
        )
    else:
        st.info("No connected provider queries have been recorded yet.")
    st.markdown("#### Provider health checks")
    if health_rows:
        smart_dataframe(pd.DataFrame(health_rows), height=430)
    else:
        st.info("No provider health checks have been recorded yet.")

with security_tab:
    policy = internet_configuration()
    section_title("Outbound policy", "🛡")
    smart_json(
        policy,
        title="Outbound connection policy",
        download_name="outbound_connection_policy.json",
        key="outbound_connection_policy",
    )
    controls = pd.DataFrame(
        [
            ("HTTPS only", "Enabled", "Provider URLs are validated before each request"),
            (
                "Official host allowlists",
                "Enabled",
                "Each connector supplies explicit approved hosts",
            ),
            ("Redirect validation", "Enabled", "Redirect destinations are revalidated and bounded"),
            (
                "Private network blocking",
                "Enabled",
                "Loopback, private, link-local and reserved IPs are rejected",
            ),
            (
                "Streaming response limits",
                "Enabled",
                "Response size is enforced while bytes are read",
            ),
            (
                "Credential redaction",
                "Enabled",
                "API keys are removed from cache metadata, provenance URLs and errors",
            ),
            (
                "Retry policy",
                "Enabled",
                "429/5xx/timeout retries use bounded backoff and Retry-After",
            ),
            (
                "Offline fallback",
                "Enabled",
                "Stale provider cache can be used when live access fails",
            ),
            (
                "Local AI boundary",
                "Enabled",
                "Ollama is restricted to the loopback endpoint 127.0.0.1:11434",
            ),
            (
                "SearXNG source separation",
                "Enabled",
                "Web snippets and official scientific records retain separate provider/source identifiers",
            ),
            (
                "OpenAI response cache",
                "Disabled",
                "Copilot requests and responses are never written to provider cache",
            ),
            (
                "Secret persistence",
                "Disabled in app",
                "Keys are not stored in project databases or exported reports",
            ),
            (
                "Provenance",
                "Enabled",
                "Retrieval time, source URL, request ID, cache state and SHA-256 are recorded",
            ),
        ],
        columns=["Control", "Status", "Evidence"],
    )
    smart_dataframe(controls, height=500)
    if st.button("Clear connected response cache"):
        removed = cache.clear()
        st.success(f"Removed {removed} cache files.")
    insight_callout(
        "Production secret management",
        "For shared or cloud deployment, inject project-scoped credentials through the platform secret manager. Do not place real keys in source files, ZIP releases, screenshots or frontend JavaScript.",
        "warning",
    )

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("provider_integration", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
