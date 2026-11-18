from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.connected.providers import (  # noqa: E402
    ENTITY_PROVIDER_DEFAULTS,
    PROVIDERS,
    ConnectedProviderService,
    provider_supports_entity,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.navigation import PAGE_BY_KEY  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="Connected Data Explorer · BioIntel AI", page_icon="🌐", layout="wide")
apply_theme()

hero(
    "Connected Data Explorer",
    "Run federated searches across official biotechnology APIs with provider compatibility checks, explicit errors and accession-level provenance.",
    eyebrow="Verified live provider integration",
    chips=["11 official APIs", "Compatibility filtering", "Typed errors", "CSV/JSON export", "Workbench handoff"],
)
scientific_boundary_banner(
    source_kind="provider_reference",
    release_eligible=False,
    message="Connected results are live or cached provider references. Review provider licences, record versions and domain-specific evidence before scientific release.",
)

entity_type = st.selectbox("Entity type", list(ENTITY_PROVIDER_DEFAULTS), index=0)
compatible = [key for key in PROVIDERS if provider_supports_entity(key, entity_type)]
default_providers = compatible
providers = st.multiselect(
    "Compatible providers",
    options=compatible,
    default=default_providers,
    format_func=lambda key: PROVIDERS[key].name,
    help="All providers that support the selected entity type are enabled by default.",
)
query = st.text_input(
    "Scientific query or accession",
    placeholder="Examples: TP53, P04637, aspirin, CHEMBL25, 4HHB, BRCA1 cancer",
)
limit = st.slider("Maximum records per provider", 1, 25, 10)

search_cols = st.columns([3, 1])
run_search = search_cols[0].button(
    "Search connected sources",
    type="primary",
    width="stretch",
    disabled=not query.strip() or not providers,
)
if search_cols[1].button("Clear results", width="stretch"):
    st.session_state.pop("connected_search_result", None)
    st.rerun()

if run_search:
    try:
        with st.status("Querying official provider APIs…", expanded=True) as status:
            status.write(f"Entity: {entity_type} · providers: {', '.join(PROVIDERS[p].name for p in providers)}")
            result = ConnectedProviderService(ROOT).universal_search(
                query,
                entity_type=entity_type,
                providers=providers,
                limit=limit,
            )
            status.write(f"Completed {len(result['provider_results'])} provider query group(s).")
            status.update(label="Connected search complete", state="complete")
        st.session_state["connected_search_result"] = result
    except Exception as exc:
        st.error(str(exc))

result = st.session_state.get("connected_search_result")
if result:
    records = result.get("records", [])
    errors = result.get("errors", [])
    skipped = result.get("skipped", [])
    provider_results = result.get("provider_results", [])
    metrics = st.columns(5)
    metrics[0].metric("Records", len(records))
    metrics[1].metric("Providers returned", len(provider_results))
    metrics[2].metric("Provider errors", len(errors))
    metrics[3].metric("Skipped", len(skipped))
    metrics[4].metric("Entity type", result.get("entity_type", ""))

    if errors:
        with st.expander("Provider errors and recovery guidance", expanded=True):
            smart_dataframe(pd.DataFrame(errors), height=240)
            error_types = {str(row.get("error_type", "")) for row in errors}
            hints = []
            if "dns_error" in error_types or "connection_error" in error_types:
                hints.append("Check Windows DNS, firewall, antivirus web shield, VPN/proxy and `BIOINTEL_INTERNET_ENABLED=1`.")
            if "authentication_error" in error_types:
                hints.append("Verify the relevant API key and project permissions.")
            if "rate_limited" in error_types:
                hints.append("Wait and retry; provider Retry-After responses are respected automatically.")
            if "not_found" in error_types:
                hints.append("Use an exact accession or a provider-supported search term.")
            for hint in hints:
                st.info(hint)
    if skipped:
        with st.expander("Skipped incompatible providers"):
            smart_dataframe(pd.DataFrame(skipped), height=200)

    if provider_results:
        section_title("Provider execution summary", "✓")
        summary_rows = [
            {
                "Provider": PROVIDERS.get(group.get("provider"), PROVIDERS["ncbi"]).name,
                "Records": len(group.get("records", [])),
                "Cache": group.get("cache_status"),
                "Latency (ms)": group.get("elapsed_ms"),
                "Request ID": group.get("request_id"),
                "Retrieved": group.get("retrieved_at_utc"),
                "Source": group.get("source_url"),
            }
            for group in provider_results
        ]
        smart_dataframe(
            pd.DataFrame(summary_rows),
            height=270,
            columns={"Source": st.column_config.LinkColumn("Provider request", display_text="Open")},
        )

    if records:
        section_title("Normalized records", "▤")
        display = pd.DataFrame(records)
        visible = [column for column in ["provider", "record_id", "record_type", "title", "summary", "score", "source_url"] if column in display.columns]
        smart_dataframe(
            display[visible],
            height=500,
            columns={
                "source_url": st.column_config.LinkColumn("Official record", display_text="Open provider"),
                "score": st.column_config.NumberColumn("Score", format="%.4f"),
            },
        )

        if len(provider_results) > 1:
            section_title("Review by provider", "🌐")
            tabs = st.tabs([PROVIDERS[group["provider"]].name for group in provider_results])
            for tab, group in zip(tabs, provider_results):
                with tab:
                    group_records = group.get("records", [])
                    if group_records:
                        frame = pd.DataFrame(group_records)
                        cols = [c for c in visible if c in frame.columns]
                        smart_dataframe(
                            frame[cols],
                            height=min(420, 100 + 34 * len(frame)),
                            columns={"source_url": st.column_config.LinkColumn("Official record", display_text="Open")},
                        )
                    else:
                        st.info("This provider returned no normalized records.")
                    if group.get("warnings"):
                        for warning in group["warnings"]:
                            st.warning(warning)

        export_frame = display.drop(columns=["payload"], errors="ignore")
        download_columns = st.columns(3)
        download_columns[0].download_button(
            "Download normalized CSV",
            export_frame.to_csv(index=False).encode("utf-8"),
            file_name="biointel_connected_results.csv",
            mime="text/csv",
            width="stretch",
        )
        download_columns[1].download_button(
            "Download evidence JSON",
            json.dumps(result, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
            file_name="biointel_connected_evidence.json",
            mime="application/json",
            width="stretch",
        )
        manifest = {
            "query": result.get("query"),
            "entity_type": result.get("entity_type"),
            "completed_at_utc": result.get("completed_at_utc"),
            "providers": [
                {
                    "provider": group.get("provider"),
                    "source_url": group.get("source_url"),
                    "sha256": group.get("sha256"),
                    "retrieved_at_utc": group.get("retrieved_at_utc"),
                    "cache_status": group.get("cache_status"),
                    "record_count": len(group.get("records", [])),
                }
                for group in provider_results
            ],
        }
        download_columns[2].download_button(
            "Download provenance manifest",
            json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
            file_name="biointel_connected_provenance.json",
            mime="application/json",
            width="stretch",
        )

        st.session_state["connected_handoff"] = {
            "query": result.get("query"),
            "entity_type": result.get("entity_type"),
            "records": records[:100],
            "provenance": manifest,
        }
        section_title("Send to a workbench", "→")
        handoffs = {
            "gene": "variant_annotation",
            "variant": "variant_annotation",
            "protein": "protein_annotation",
            "structure": "structural_bioinformatics",
            "compound": "drug_analyzer",
            "pathway": "pathway_network",
            "protein interaction": "ppi_interaction_ml",
            "expression study": "transcriptomics_expression",
            "sequence": "sequence_analyzer",
            "literature": "knowledge_search",
            "clinical trial": "scientific_evidence_excellence",
        }
        target = PAGE_BY_KEY.get(handoffs.get(entity_type, "biointel_studio"))
        if target:
            st.page_link(target.path, label=f"Open {target.title}", width="stretch")
        st.caption("Normalized records and provenance are stored in the current Streamlit session as `connected_handoff`.")
    else:
        badge("● No records returned; refine the query or inspect provider errors", "warning")

section_title("Provider coverage", "🌐")
coverage = pd.DataFrame(
    [
        {
            "Provider": spec.name,
            "Domains": ", ".join(spec.domains),
            "Query mode": "Free text / accession" if spec.supports_free_text else "Exact symbol / identifier",
            "Rate (rps)": spec.requests_per_second,
            "Description": spec.description,
            "API": spec.base_url,
            "Documentation": spec.documentation_url,
        }
        for spec in PROVIDERS.values()
    ]
)
smart_dataframe(
    coverage,
    height=450,
    columns={
        "API": st.column_config.LinkColumn("Official API", display_text="Open"),
        "Documentation": st.column_config.LinkColumn("Documentation", display_text="Docs"),
    },
)
insight_callout(
    "Live-data boundary",
    "Provider APIs can change, throttle, temporarily fail or return records with different review status. BioIntel preserves the provider URL, retrieval time, cache state and response checksum so results can be audited.",
    "info",
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='connected_data_explorer', title='Connected Data Explorer', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
