from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.connected.copilot import OpenAICopilot, evidence_only_answer  # noqa: E402
from biointel.connected.diagnostics import test_openai_connection  # noqa: E402
from biointel.connected.free_web_ai import (  # noqa: E402
    FreeWebCopilot,
    free_web_stack_diagnostic,
)
from biointel.connected.providers import PROVIDERS, ConnectedProviderService  # noqa: E402
from biointel.connected.registry import recent_copilot_runs  # noqa: E402
from biointel.ui.components import (  # noqa: E402
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import indeterminate_loader

REGISTRY = ROOT / "reports" / "connected_sources.sqlite3"

st.set_page_config(page_title="BioIntel Copilot · BioIntel AI", page_icon="🤖", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('offline_copilot_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'offline_copilot_core', expanded=False)

hero(
    "BioIntel Copilot",
    "Use free local Ollama + SearXNG web research, official scientific providers, OpenAI, or evidence-only retrieval.",
    eyebrow="Free web-connected AI · official scientific evidence · optional OpenAI",
    chips=[
        "Free Ollama AI",
        "SearXNG web search",
        "11 provider tools",
        "Accession citations",
        "No key persistence",
        "Research-use boundary",
    ],
)
scientific_boundary_banner(
    source_kind="provider_reference",
    release_eligible=False,
    message=(
        "Provider records and AI synthesis are research aids. They do not establish experimental truth, diagnosis, treatment, regulatory status or clinical validity. "
        "Free Local + Web mode keeps AI generation on this computer through Ollama; web queries go to the selected SearXNG instance and official scientific providers. OpenAI is used only when explicitly selected."
    ),
)

st.session_state.setdefault("copilot_messages", [])
st.session_state.setdefault("openai_connection_test", None)
st.session_state.setdefault("free_web_connection_test", None)


def infer_entity_type(question: str) -> str:
    lowered = question.lower()
    rules = [
        ("protein interaction", ["interaction", "ppi", "protein-protein"]),
        ("clinical trial", ["trial", "clinical study", "recruiting"]),
        ("structure", ["structure", "pdb", "crystal", "cryo-em"]),
        ("variant", ["variant", "mutation", "clinvar", "snv", "indel"]),
        ("compound", ["drug", "compound", "molecule", "smiles", "chembl", "pubchem"]),
        ("pathway", ["pathway", "reactome", "enrichment"]),
        ("protein", ["protein", "uniprot", "domain", "interpro"]),
        ("expression study", ["geo", "expression", "rna-seq", "transcriptomic"]),
        ("sequence", ["fasta", "sequence", "nucleotide", "genbank"]),
        ("gene", ["gene", "genomic", "ensembl"]),
    ]
    for entity, tokens in rules:
        if any(token in lowered for token in tokens):
            return entity
    return "literature"


with st.sidebar:
    st.markdown("### AI connection")
    environment_key = os.getenv("OPENAI_API_KEY", "").strip()
    active_key = environment_key
    model = os.getenv("OPENAI_MODEL", "gpt-5.5")
    ollama_model = os.getenv("BIOINTEL_OLLAMA_MODEL", "gemma3:1b")
    searxng_url = os.getenv("SEARXNG_URL", "")

    mode = st.radio(
        "Answer mode",
        ["Free Local + Web", "Evidence only", "OpenAI Copilot"],
        index=0,
        help="Free Local + Web uses Ollama locally plus SearXNG and official scientific providers. No paid AI API key is required.",
    )

    if mode == "Free Local + Web":
        st.markdown("#### Ollama + SearXNG")
        ollama_model = st.text_input(
            "Ollama model",
            value=ollama_model,
            key="copilot_ollama_model",
            help="Default lightweight model: gemma3:1b. The installer attempts to download it once.",
        )
        searxng_url = st.text_input(
            "Private SearXNG URL (optional)",
            value=searxng_url,
            key="copilot_searxng_url",
            placeholder="Leave blank for automatic healthy-instance discovery",
        )
        if st.button("Test free web AI", width="stretch"):
            with indeterminate_loader("Testing Ollama, model and SearXNG search…"):
                st.session_state["free_web_connection_test"] = free_web_stack_diagnostic(
                    ROOT, model=ollama_model, searxng_url=searxng_url or None
                )
        free_test = st.session_state.get("free_web_connection_test")
        if free_test:
            if free_test.get("ready"):
                st.success("Free Web AI connected")
            else:
                ollama_error = free_test.get("ollama", {}).get("error", "")
                searx_error = free_test.get("searxng", {}).get("error", "")
                st.warning(ollama_error or searx_error or "Free Web AI is not ready yet.")
    elif mode == "OpenAI Copilot":
        st.markdown("#### OpenAI connection")
        session_key = st.text_input(
            "Session-only API key",
            type="password",
            value="",
            help="Optional. Kept only in this Streamlit session and never written to project files or databases.",
            key="copilot_session_key_input",
        )
        active_key = session_key.strip() or environment_key
        model = st.text_input(
            "OpenAI model", value=model, key="copilot_model"
        )
        if st.button("Test OpenAI connection", width="stretch", disabled=not active_key):
            with indeterminate_loader("Validating API key and model visibility…"):
                st.session_state["openai_connection_test"] = test_openai_connection(
                    ROOT, api_key=active_key, model=model
                )
        connection_test = st.session_state.get("openai_connection_test")
        if connection_test:
            if connection_test.get("available") and connection_test.get("model_visible"):
                st.success(f"Connected · {connection_test.get('model')} available")
            elif connection_test.get("available"):
                st.warning(connection_test.get("error") or "Key valid, selected model not listed.")
            else:
                st.error(connection_test.get("error") or "Connection failed.")

    enabled_providers = st.multiselect(
        "Official scientific providers",
        options=list(PROVIDERS),
        default=list(PROVIDERS),
        format_func=lambda key: PROVIDERS[key].name,
    )
    use_web_search = st.checkbox(
        "Use SearXNG web search",
        value=True,
        disabled=mode != "Free Local + Web",
        help="Searches current public web results. Official provider evidence remains separately identified.",
    )
    use_scientific_providers = st.checkbox(
        "Use official scientific providers",
        value=True,
        disabled=mode == "OpenAI Copilot",
    )
    st.caption("Core app flow remains INSTALL_WINDOWS.bat → RUN_BOTH_WINDOWS.bat.")

status_columns = st.columns(5)
status_columns[0].metric("Local AI", ollama_model if mode == "Free Local + Web" else "Standby")
status_columns[1].metric("OpenAI key", "Configured" if active_key else "Optional")
status_columns[2].metric("Provider tools", len(enabled_providers))
status_columns[3].metric("Mode", mode)
status_columns[4].metric(
    "Stored responses",
    "Off"
    if os.getenv("OPENAI_STORE_RESPONSES", "0").lower() in {"0", "false", "no", "off", ""}
    else "On",
)

if mode == "Free Local + Web":
    badge("● Free local Ollama generation with SearXNG and official-provider grounding", "success")
elif mode == "OpenAI Copilot" and active_key:
    badge(
        "● OpenAI is configured; run the connection test before the first scientific query",
        "success",
    )
elif mode == "OpenAI Copilot":
    badge("● Add an OpenAI API key or switch to Evidence only", "warning")
else:
    badge("● Evidence-only mode will not send your question to OpenAI", "info")

context = st.text_area(
    "Optional local context",
    placeholder="Paste a short sequence description, project question or selected result summary. Avoid confidential patient data.",
    height=110,
    max_chars=20000,
)

for message in st.session_state["copilot_messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("evidence"):
            with st.expander(f"Provider evidence ({len(message['evidence'])} result groups)"):
                for group in message["evidence"]:
                    provider = group.get("provider", "provider")
                    records = group.get("records", [])
                    st.markdown(
                        f"**{PROVIDERS.get(provider, PROVIDERS['ncbi']).name if provider in PROVIDERS else provider}** · {len(records)} record(s)"
                    )
                    if records:
                        frame = pd.DataFrame(records)
                        columns = [
                            c
                            for c in ["record_id", "record_type", "title", "summary", "source_url"]
                            if c in frame.columns
                        ]
                        smart_dataframe(
                            frame[columns],
                            height=min(340, 80 + len(frame) * 34),
                            columns={
                                "source_url": st.column_config.LinkColumn(
                                    "Official record", display_text="Open"
                                )
                            },
                        )

question = st.chat_input(
    "Ask about a gene, protein, compound, pathway, structure, variant, trial or publication"
)
if question:
    st.session_state["copilot_messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.status("Running grounded scientific workflow…", expanded=True) as status:
                if mode == "Free Local + Web":
                    if not use_web_search and not use_scientific_providers:
                        raise ValueError("Enable SearXNG web search or official scientific providers.")
                    status.write("Retrieving current web and official scientific evidence before local AI generation.")
                    result = FreeWebCopilot(
                        ROOT,
                        model=ollama_model,
                        searxng_url=searxng_url or None,
                    ).run(
                        question,
                        allowed_providers=enabled_providers,
                        context=context,
                        use_web_search=use_web_search,
                        use_scientific_providers=use_scientific_providers,
                    )
                elif mode == "OpenAI Copilot":
                    if not active_key:
                        raise ValueError("OpenAI API key is required for OpenAI Copilot mode.")
                    if not enabled_providers:
                        raise ValueError("Select at least one approved provider tool.")
                    status.write("OpenAI may call only the provider tools selected in the sidebar.")
                    result = OpenAICopilot(ROOT, api_key=active_key, model=model).run(
                        question,
                        allowed_providers=enabled_providers,
                        context=context,
                    )
                else:
                    entity_type = infer_entity_type(question)
                    status.write(f"Evidence-only search inferred entity type: {entity_type}.")
                    payload = ConnectedProviderService(ROOT).universal_search(
                        question,
                        entity_type=entity_type,
                        providers=enabled_providers,
                        limit=6,
                    )
                    result = evidence_only_answer(question, payload)
                status.update(label="Copilot workflow completed", state="complete")
            st.markdown(result.answer)
            st.caption(
                f"Run {result.run_id} · mode {result.mode} · model {result.model} · "
                f"tool calls {result.tool_calls} · tokens {result.input_tokens}/{result.output_tokens}"
            )
            if result.evidence:
                with st.expander(
                    f"Provider evidence ({len(result.evidence)} groups)", expanded=True
                ):
                    for group in result.evidence:
                        smart_json(
                            group,
                            title="Provider evidence group",
                            expanded=False,
                            download_name="copilot_provider_evidence.json",
                        )
            st.session_state["copilot_messages"].append(
                {"role": "assistant", "content": result.answer, "evidence": list(result.evidence)}
            )
        except Exception as exc:
            st.error(str(exc))
            st.session_state["copilot_messages"].append(
                {"role": "assistant", "content": f"Run failed safely: {exc}"}
            )

buttons = st.columns(2)
if buttons[0].button("Clear conversation", width="stretch"):
    st.session_state["copilot_messages"] = []
    st.rerun()
if buttons[1].button("Export conversation JSON", width="stretch"):
    st.download_button(
        "Download conversation",
        json.dumps(st.session_state["copilot_messages"], indent=2, default=str).encode("utf-8"),
        file_name="biointel_copilot_conversation.json",
        mime="application/json",
        width="stretch",
    )

section_title("Connection and evidence controls", "✓")
controls = pd.DataFrame(
    [
        (
            "Secret handling",
            "Environment variable or session-only input; never stored in connected_sources.sqlite3",
        ),
        (
            "Free local AI",
            "Ollama generation runs on loopback only; no paid AI API key is required",
        ),
        (
            "Free web search",
            "SearXNG private URL or automatic healthy public-instance discovery with explicit source links",
        ),
        (
            "Connection validation",
            "Ollama, model, SearXNG, OpenAI and official providers can be tested independently",
        ),
        ("Tool allowlist", "Only providers selected by the operator are exposed to OpenAI"),
        (
            "Data minimization",
            "Raw provider payloads stay local; compact normalized evidence is sent to OpenAI",
        ),
        (
            "Citation contract",
            "Answers are instructed to cite [provider:record_id], plus an automatic verified-source footer",
        ),
        (
            "Provenance",
            "Provider URL, checksum, cache state, request ID and retrieval time are recorded locally",
        ),
        (
            "Failure behavior",
            "Authentication, DNS, timeout, rate-limit and provider errors remain explicit",
        ),
    ],
    columns=["Control", "Implementation"],
)
smart_dataframe(controls, height=340)

runs = recent_copilot_runs(REGISTRY, limit=30)
if runs:
    section_title("Recent Copilot runs", "◴")
    smart_dataframe(pd.DataFrame(runs), height=330)

insight_callout(
    "Cost, privacy and external validation",
    "Free Local + Web mode has no paid AI API requirement, but it downloads an Ollama model and public SearXNG instances can rate-limit or become unavailable. For sensitive work, use a private SearXNG instance. Do not submit confidential patient data to public web services.",
    "info",
)

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("offline_copilot_core", None, key_prefix="step114_offline_copilot_core", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='biointel_copilot', title='BioIntel Copilot', category='Intelligence')

# STEP177_21_MODULE_MODEL_COHORT_RUNTIME_EXCELLENCE
from biointel.target_modules_v177.ui import render_step177_module_upgrade
render_step177_module_upgrade('offline_copilot_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("offline_copilot_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("offline_copilot_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('offline_copilot_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('offline_copilot_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('offline_copilot_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('offline_copilot_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('offline_copilot_core', expanded=False)

