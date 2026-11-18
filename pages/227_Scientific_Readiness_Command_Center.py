from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific_depth import (
    CAPABILITY_SPECS,
    MODULE_PROFILES,
    assess_evidence_readiness,
    build_evidence_manifest_template,
    scientific_portfolio_catalog,
    scientific_portfolio_manifest,
    scientific_portfolio_summary,
    native_portfolio_manifest,
    native_input_template,
    native_template_manifest,
    run_native_workflow,
    detect_specialist_toolchains,
    reference_readiness,
    toolchain_summary,
    portfolio_readiness_matrix,
    readiness_summary,
    profile_tabular_file,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import render_upload_preflight, stage_streamlit_upload

st.set_page_config(page_title="Scientific Readiness Command Center · BioIntel AI", page_icon="SR", layout="wide")
apply_theme()
hero(
    "Scientific Readiness Command Center",
    "Audit scientific depth, specialist-engine coverage, reference provenance, evidence completeness and fail-closed release gates across the BioIntel AI portfolio.",
    eyebrow="BioIntel AI · Step 159 Portfolio Qualification & Runtime Resilience",
    chips=["80/80 implementation contracts", "78 protected engine plans", "Streaming full-file profiler", "Evidence manifests", "Independent validation gates", "Auditable exports"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="This command center measures software and evidence readiness. It does not create experimental evidence, clinical validation, regulatory authorization or laboratory accreditation.",
)

catalog = scientific_portfolio_catalog()
summary = scientific_portfolio_summary(catalog)
metric_cards(
    [
        ("Covered modules", summary["modules"], "Registered depth profiles"),
        ("Complete contracts", f"{summary['complete_contracts']}/{summary['modules']}", "Six-stage + validation boundary"),
        ("Pipeline stages", summary["pipeline_stages"], "Built-in, adapter and external"),
        ("Native workflows", summary["native_engines"], "Locally available deterministic cores"),
        ("Validation gates", summary["validation_gates"], "Module-specific requirements"),
    ]
)

section_title("Portfolio contract matrix", "🧭")
filter_cols = st.columns(3)
query = filter_cols[0].text_input("Search module", value="", key="step151_portfolio_query")
contract_filter = filter_cols[1].selectbox("Contract status", ["All", "Complete", "Incomplete"], key="step151_contract_filter")
min_adapters = filter_cols[2].number_input("Minimum adapter stages", min_value=0, max_value=20, value=0, step=1, key="step151_adapter_filter")
view = catalog.copy()
if query.strip():
    token = query.strip().casefold()
    view = view.loc[view["module_key"].str.casefold().str.contains(token, regex=False) | view["title"].str.casefold().str.contains(token, regex=False)]
if contract_filter == "Complete":
    view = view.loc[view["minimum_contract_complete"].astype(bool)]
elif contract_filter == "Incomplete":
    view = view.loc[~view["minimum_contract_complete"].astype(bool)]
view = view.loc[view["adapter_stages"] >= int(min_adapters)]
smart_dataframe(view, height=500, key="step151_portfolio_catalog")

section_title("Specialist toolchain and reference readiness", "🧰")
toolchains = detect_specialist_toolchains()
tool_summary = toolchain_summary(toolchains)
metric_cards([
    ("Specialist engines", tool_summary["engines"], "Referenced external toolchains"),
    ("Detected locally", tool_summary["available"], "Executable or Python package"),
    ("Missing", tool_summary["missing"], "Native fallback remains available"),
    ("All specialist tools", "Yes" if tool_summary["all_specialist_toolchains_available"] else "No", "Never implied by native fallback"),
])
smart_dataframe(toolchains, height=430, key="step154_toolchain_catalog")
with st.expander("Reference-asset candidates", expanded=False):
    reference_table = reference_readiness(ROOT)
    smart_dataframe(reference_table, height=420, key="step157_reference_readiness")

# Backward compatibility label: Step 157 honest 10/10 readiness matrix
section_title("Step 159 honest readiness matrix", "🎯")
@st.cache_data(show_spinner=False, ttl=120)
def _step159_readiness_matrix() -> pd.DataFrame:
    return portfolio_readiness_matrix(ROOT, detect_runtime=True)

readiness_matrix = _step159_readiness_matrix()
readiness_totals = readiness_summary(readiness_matrix)
metric_cards([
    ("Implementation-complete", f"{readiness_totals['implementation_complete']}/{readiness_totals['modules']}", "Code-owned module contracts"),
    ("Specialist-runtime complete", f"{readiness_totals['specialist_runtime_complete']}/{readiness_totals['modules']}", "Installed engines + references"),
    ("External-evidence complete", f"{readiness_totals['external_evidence_complete']}/{readiness_totals['modules']}", "Independent/prospective evidence"),
    ("Release eligible", readiness_totals["release_eligible"], "All three axes complete"),
])
st.caption("Internal implementation, specialist runtime qualification and external scientific evidence are scored independently. Passing software tests never fabricates clinical or wet-lab evidence.")
score_filter = st.selectbox(
    "Readiness view",
    ["All modules", "Implementation below 100", "Specialist runtime incomplete", "External evidence incomplete"],
    key="step159_readiness_filter",
)
readiness_view = readiness_matrix.copy()
if score_filter == "Implementation below 100":
    readiness_view = readiness_view.loc[readiness_view.internal_implementation_score < 100]
elif score_filter == "Specialist runtime incomplete":
    readiness_view = readiness_view.loc[readiness_view.specialist_runtime_score < 100]
elif score_filter == "External evidence incomplete":
    readiness_view = readiness_view.loc[readiness_view.external_evidence_score < 100]
smart_dataframe(readiness_view, height=500, key="step159_readiness_matrix")
st.download_button(
    "Download complete readiness matrix",
    data=readiness_matrix.to_csv(index=False).encode("utf-8"),
    file_name="biointel_step159_module_readiness_matrix.csv",
    mime="text/csv",
    key="step157_readiness_download",
    width="stretch",
)

section_title("Module evidence workbench", "🧾")
module_key = st.selectbox(
    "Scientific module",
    catalog["module_key"].tolist(),
    format_func=lambda key: f"{MODULE_PROFILES[key].title} · {key}",
    key="step151_module_key",
)
profile = MODULE_PROFILES[module_key]
spec = CAPABILITY_SPECS[module_key]
left, right = st.columns([1.15, 1])
with left:
    stage_rows = [
        {
            "stage": stage.label,
            "mode": stage.mode,
            "purpose": stage.purpose,
            "required_columns": ", ".join(stage.required_columns),
            "engines": ", ".join(stage.engines),
            "references": ", ".join(stage.references),
            "validation_gate": stage.validation_gate,
        }
        for stage in spec.stages
    ]
    smart_dataframe(pd.DataFrame(stage_rows), height=390, key="step151_stage_contract")
with right:
    st.markdown("**Module release blockers**")
    for blocker in spec.release_blockers:
        st.markdown(f"- {blocker}")
    st.warning(spec.evidence_boundary)

st.caption("Upload a harmonized CSV/TSV table to assess schema, data integrity, design signals and evidence declarations for the selected module.")
native_template = native_input_template(module_key)
native_demo = native_input_template(module_key, demonstration=True)
native_template_info = native_template_manifest(module_key)
template_cols = st.columns(3)
template_cols[0].download_button(
    "Download empty input template",
    data=native_template.to_csv(index=False).encode("utf-8"),
    file_name=f"{module_key}_step159_input_template.csv",
    mime="text/csv",
    width="stretch",
)
template_cols[1].download_button(
    "Download runnable demo dataset",
    data=native_demo.to_csv(index=False).encode("utf-8"),
    file_name=f"{module_key}_step159_demo.csv",
    mime="text/csv",
    width="stretch",
)
template_cols[2].download_button(
    "Download template manifest",
    data=json.dumps(native_template_info, indent=2).encode("utf-8"),
    file_name=f"{module_key}_step159_template_manifest.json",
    mime="application/json",
    width="stretch",
)
upload = st.file_uploader("Optional module dataset", type=["csv", "tsv"], key="step151_readiness_upload")
upload_profile = render_upload_preflight(
    upload,
    key="step151_readiness_upload_preflight",
    allowed_extensions=["csv", "tsv"],
    soft_limit_mb=100,
    hard_limit_mb=1024,
    module_key="scientific_readiness_command_center",
)
data = pd.DataFrame()
source_mode = "no_data"
if upload is not None:
    try:
        separator = "\t" if str(upload.name).lower().endswith(".tsv") else ","
        data = pd.read_csv(upload, sep=separator)
        source_mode = "uploaded"
        smart_dataframe(data.head(1_000), height=280, key="step151_readiness_preview")
    except Exception as exc:
        st.error(f"Dataset could not be read: {exc}")

with st.expander("Full-file streaming integrity profiler", expanded=False):
    st.caption("Profiles every CSV/TSV row with bounded memory, full-file SHA-256, atomic checkpoints, schema-drift detection and complete downloadable evidence.")
    stream_chunk_rows = st.number_input(
        "Rows per streaming chunk",
        min_value=1_000,
        max_value=1_000_000,
        value=100_000,
        step=10_000,
        key="step159_stream_chunk_rows",
    )
    if upload is None:
        st.info("Upload a CSV/TSV file above to enable the streaming profiler.")
    elif st.button("Run full-file streaming profile", key="step159_stream_run", width="stretch"):
        try:
            suffix = ".tsv" if str(upload.name).lower().endswith(".tsv") else ".csv"
            runtime_dir = Path(tempfile.gettempdir()) / "biointel_step159_streaming"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            identity = (upload_profile.sha256 if upload_profile is not None else "")[:16]
            target = runtime_dir / f"{module_key}_{identity or 'upload'}{suffix}"
            stage_streamlit_upload(upload, target, max_bytes=1024 * 1024 * 1024)
            checkpoint = target.with_suffix(target.suffix + ".checkpoint.json")
            with st.spinner("Profiling the complete file with bounded memory…"):
                stream_result = profile_tabular_file(
                    target,
                    chunk_rows=int(stream_chunk_rows),
                    checkpoint_path=checkpoint,
                    expected_columns=native_template.columns,
                    resume=True,
                )
            st.session_state["step157_stream_result"] = stream_result.to_dict()
            st.session_state["step157_stream_bundle"] = stream_result.bundle()
        except Exception as exc:
            st.error(f"Streaming profile stopped safely: {type(exc).__name__}: {exc}")
    stream_payload = st.session_state.get("step157_stream_result")
    if isinstance(stream_payload, dict):
        metric_cards([
            ("Rows profiled", f"{int(stream_payload['rows']):,}", "Complete file"),
            ("Columns", stream_payload["columns"], "Schema"),
            ("Chunks", stream_payload["chunks"], "Checkpointed"),
            ("Schema drift", "Yes" if stream_payload["schema_drift_detected"] else "No", "Across chunks"),
        ])
        smart_dataframe(pd.DataFrame(stream_payload["column_profile"]), height=420, key="step157_stream_profile_table")
        for recommendation in stream_payload.get("recommendations", []):
            st.info(recommendation)
        bundle = st.session_state.get("step157_stream_bundle")
        if isinstance(bundle, (bytes, bytearray)):
            st.download_button(
                "Download checksum-bound streaming profile bundle",
                data=bundle,
                file_name=f"{module_key}_step157_streaming_profile.zip",
                mime="application/zip",
                key="step157_stream_bundle_download",
                width="stretch",
            )

section_title("Step 157 adaptive and streaming execution", "⚙️")
analysis_mode = st.selectbox(
    "Analysis mode",
    ["interactive", "extended", "full"],
    format_func=lambda value: {
        "interactive": "Interactive · 250k rows / 100 features",
        "extended": "Extended · 750k rows / 256 features",
        "full": "Full desktop · 1M rows / 512 features",
    }[value],
    key="step157_analysis_mode",
)
if data.empty:
    st.info("Upload a CSV/TSV table to execute the selected module's deterministic local workflow.")
else:
    native_result = run_native_workflow(module_key, data, metadata={"analysis_mode": analysis_mode})
    metric_cards([
        ("Native status", native_result.status.title(), "Pass, review or fail-closed"),
        ("Rows analyzed", f"{native_result.summary['rows_analyzed']:,}", "Bounded local execution"),
        ("Checks passed", native_result.summary["checks_passed"], "Automatic checks"),
        ("Derived tables", native_result.summary["tables_generated"], "Module-family outputs"),
    ])
    native_tabs = st.tabs(["Checks", "Metrics", "Derived tables", "Native manifest"])
    with native_tabs[0]:
        smart_dataframe(native_result.checks, height=380, key="step157_native_checks")
    with native_tabs[1]:
        smart_dataframe(native_result.metrics, height=320, key="step157_native_metrics")
    with native_tabs[2]:
        for table_name, table in native_result.tables.items():
            if not table.empty:
                with st.expander(table_name.replace("_", " ").title(), expanded=False):
                    smart_dataframe(table, height=360, key=f"step157_native_{table_name}")
    with native_tabs[3]:
        smart_json(native_result.manifest, title="Native scientific run manifest", download_name=f"{module_key}_step157_native.json", key="step157_native_manifest")
        st.download_button(
            "Download complete native result bundle",
            data=native_result.complete_bundle,
            file_name=f"{module_key}_step157_complete_native_results.zip",
            mime="application/zip",
            key="step157_native_bundle",
            width="stretch",
        )

template = build_evidence_manifest_template(
    module_key,
    profile_references=profile.references,
    profile_validations=profile.validations,
)
evidence_text = st.text_area(
    "Evidence declaration JSON",
    value=json.dumps(template, indent=2),
    height=300,
    key=f"step151_evidence_{module_key}",
)
try:
    evidence = json.loads(evidence_text)
    if not isinstance(evidence, dict):
        raise ValueError("Evidence declaration must be a JSON object")
except (json.JSONDecodeError, ValueError) as exc:
    st.error(f"Evidence declaration is invalid: {exc}")
    evidence = {}

readiness = assess_evidence_readiness(
    module_key,
    data,
    profile_references=profile.references,
    profile_validations=profile.validations,
    metadata=evidence,
    source_mode=source_mode,
)
metric_cards(
    [
        ("Readiness", f"{readiness.score:.0f}/100", f"Grade {readiness.grade}"),
        ("Data quality", f"{readiness.data_quality_score:.0f}/30", "Input integrity"),
        ("Evidence blockers", len(readiness.blockers), "Fail-closed"),
        ("Release ready", "Yes" if readiness.release_ready else "No", "Independent evidence required"),
    ]
)
readiness_tabs = st.tabs(["Checks", "Evidence requirements", "Manifest"])
with readiness_tabs[0]:
    smart_dataframe(readiness.checks, height=430, key="step151_readiness_checks")
with readiness_tabs[1]:
    smart_dataframe(readiness.requirements, height=430, key="step151_readiness_requirements")
with readiness_tabs[2]:
    smart_json(readiness.manifest, title="Module readiness manifest", download_name=f"{module_key}_step155_readiness.json", key="step151_module_manifest")

portfolio_manifest = scientific_portfolio_manifest()
portfolio_manifest["native_portfolio"] = native_portfolio_manifest()
st.download_button(
    "Download complete scientific portfolio manifest",
    data=json.dumps(portfolio_manifest, indent=2, default=str).encode("utf-8"),
    file_name="biointel_step155_scientific_portfolio.json",
    mime="application/json",
    type="primary",
    width="stretch",
)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
