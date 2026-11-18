from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.jobs.local_queue import LocalJobQueue
from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan, engine_status_matrix, plan_catalog, plan_to_dict
from biointel.native.formats import (
    INTERACTIVE_NATIVE_BYTES,
    MAX_NATIVE_FILE_BYTES,
    NATIVE_FORMATS,
    format_matrix,
    parse_native_source,
)
from biointel.statistics.rigor import (
    benjamini_hochberg,
    bootstrap_confidence_interval,
    two_group_disclosure,
)
from biointel.ui.components import metric_cards, scientific_table, smart_dataframe
from biointel.ui.theme import apply_theme
from biointel.ui.viewer_sync import ViewerSyncStore, active_project_key
from biointel.ui.workbench import compact_module_header, stage_large_upload
from biointel.ui.workflow import render_upload_preflight

USER_ROOT = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or ROOT / "UserData")
ENGINE_WORKSPACE = USER_ROOT / "native_engine_workspace"
ENGINE_WORKSPACE.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Real Engine & Native Format Integration · BioIntel AI", page_icon="⚙️", layout="wide")
apply_theme()
compact_module_header(
    title="Real Engine & Native Format Integration",
    summary=(
        "Decode native scientific evidence, inspect real engine readiness, prepare shell-free execution plans, "
        "standardise statistical disclosure and synchronize selections across advanced scientific viewers."
    ),
    icon="⚙️",
    category="Scientific Infrastructure",
    tags=("Native formats", "External engines", "Statistics", "Viewer sync"),
    boundary=(
        "BioIntel executes only explicitly configured local engines and never treats a heuristic fallback as a native engine result. "
        "Clinical, diagnostic, regulated and vendor-certified interpretation still requires validated procedures and specialist review."
    ),
)

metric_cards(
    [
        ("Native formats", len(NATIVE_FORMATS), "Streaming and bounded parsers"),
        ("External engines", len(ENGINE_REGISTRY), "Version-probed locally"),
        ("Upload ceiling", "1 GB", "100 MB interactive threshold"),
        ("Execution safety", "Shell-free", "Protected workspace and checksums"),
    ]
)


def _read_table(upload) -> pd.DataFrame:
    suffix = Path(upload.name).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(upload)
    if suffix == ".tsv":
        return pd.read_csv(upload, sep="\t")
    return pd.read_csv(upload)


@st.cache_data(ttl=60, show_spinner=False)
def _engine_matrix_cached() -> pd.DataFrame:
    return engine_status_matrix()


tabs = st.tabs([
    "Native scientific files",
    "Real engine readiness",
    "Statistical rigor",
    "Viewer synchronization",
    "Scientific quality gates",
])

with tabs[0]:
    st.subheader("Native format coverage")
    st.caption("Built-in readers decode supported files directly. Engine-assisted formats remain clearly labelled and are never silently replaced by proxy values.")
    scientific_table(format_matrix(), key="step111_format_matrix", file_name="native_format_matrix.csv", selectable=False, height=420)

    all_extensions = sorted({extension for spec in NATIVE_FORMATS.values() for extension in spec.extensions})
    upload = st.file_uploader(
        "Upload a native scientific file",
        type=all_extensions,
        key="step111_native_upload",
        help="Maximum 1 GB per file. Files above 100 MB are staged for background-safe parsing.",
    )
    native_upload_profile = render_upload_preflight(
        upload,
        key="step111_native_upload",
        allowed_extensions=all_extensions,
        soft_limit_mb=100,
        hard_limit_mb=1024,
        block_large_files=False,
        module_key="native_format_integration",
    )
    viewer = st.selectbox(
        "Preferred viewer context",
        ["Auto-detect"] + sorted({viewer for spec in NATIVE_FORMATS.values() for viewer in spec.viewer_keys}),
        key="step111_native_viewer",
    )
    max_records = st.select_slider("Bounded preview record limit", [5_000, 10_000, 25_000, 50_000, 100_000, 250_000], value=50_000)
    if upload is not None and native_upload_profile is not None:
        size = int(native_upload_profile.size_bytes)
        upload_identity = f"{getattr(upload, 'file_id', '')}:{upload.name}:{size}"
        if st.session_state.get("step111_native_upload_identity") != upload_identity:
            st.session_state["step111_native_upload_identity"] = upload_identity
            st.session_state.pop("step111_native_result", None)
        st.caption(f"File size: {size / 1024 / 1024:.2f} MB · SHA-256 and parser provenance will be recorded")
        if size > MAX_NATIVE_FILE_BYTES:
            st.error("The file exceeds the 1 GB per-file limit.")
        elif size > INTERACTIVE_NATIVE_BYTES:
            if st.button("Stage and queue native parser", type="primary", key="step111_stage_native"):
                manifest = stage_large_upload(upload, module_key="step111_native", project_root=ROOT)
                queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
                job = queue.submit(
                    "native_format_parse",
                    {
                        "path": manifest["staged_path"],
                        "viewer_key": "" if viewer == "Auto-detect" else viewer,
                        "max_records": int(max_records),
                    },
                    priority=70,
                    max_attempts=2,
                    stages=["detect", "parse", "validate", "finalize"],
                    resources={"io_bound": True, "memory_mb": 1024},
                )
                st.success(f"Native parser queued: {job.job_id}")
                st.code(json.dumps({**manifest, "native_parse_job_id": job.job_id, "staged_path": "protected UserData staging path"}, indent=2), language="json")
        else:
            if st.button("Parse native file", type="primary", key="step111_parse_native"):
                with st.spinner("Decoding native scientific evidence…"):
                    result = parse_native_source(
                        upload,
                        preferred_viewer=None if viewer == "Auto-detect" else viewer,
                        max_records=int(max_records),
                    )
                st.session_state["step111_native_result"] = result
            result = st.session_state.get("step111_native_result")
            if result is not None:
                summary = result.summary()
                summary.pop("preview_array", None)
                st.success(f"Decoded {result.format_key.upper()} · {result.record_count:,} preview records")
                st.code(json.dumps(summary, indent=2, default=str), language="json")
                if result.warnings:
                    for warning in result.warnings:
                        st.warning(warning)
                if not result.primary.empty:
                    scientific_table(result.primary.head(50_000), key="step111_native_primary", file_name="native_primary_preview.csv", height=420)
                for name, frame in result.secondary.items():
                    if frame.empty:
                        continue
                    with st.expander(f"Secondary native table: {name}", expanded=False):
                        smart_dataframe(frame.head(50_000), height=360, key=f"step111_secondary_{name}")

with tabs[1]:
    st.subheader("External scientific-engine readiness")
    if st.button("Scan local engine versions", type="primary", key="step111_scan_engines"):
        with st.spinner("Probing local executables and Python adapters…"):
            st.session_state["step111_engine_status"] = _engine_matrix_cached()
    status = st.session_state.get("step111_engine_status", pd.DataFrame())
    available = int(status["Available"].sum()) if not status.empty else 0
    metric_cards([
        ("Registered engines", len(ENGINE_REGISTRY), "Version probes run only on request"),
        ("Detected", available if not status.empty else "Not scanned", "Executable and version probe"),
        ("Protected workspace", ENGINE_WORKSPACE.name, "Paths cannot escape UserData"),
        ("Execution mode", "Background queue", "Pause/cancel/retry capable"),
    ])
    if status.empty:
        st.info("Run the local engine scan to inspect executable paths and versions. Missing tools remain unavailable rather than being replaced by a fake result.")
    else:
        scientific_table(status, key="step111_engine_matrix", file_name="engine_readiness.csv", selectable=False, height=520)
    st.subheader("Validated execution plans")
    scientific_table(plan_catalog(), key="step111_plan_catalog", file_name="engine_plan_catalog.csv", selectable=False, height=360)

    selected_plan = st.selectbox("Prepare execution plan", plan_catalog()["Plan"].tolist(), key="step111_plan")
    st.caption("All file paths must already exist inside the protected native-engine workspace. Commands are built as argument lists and never passed through a shell.")
    examples = {
        "samtools_index": {"alignment": str(ENGINE_WORKSPACE / "sample.bam"), "threads": 2},
        "samtools_depth": {"alignment": str(ENGINE_WORKSPACE / "sample.bam"), "output": str(ENGINE_WORKSPACE / "coverage.tsv"), "region": "chr1:1-100000", "threads": 2},
        "bcftools_norm": {"vcf": str(ENGINE_WORKSPACE / "input.vcf.gz"), "reference": str(ENGINE_WORKSPACE / "reference.fa"), "output": str(ENGINE_WORKSPACE / "normalized.vcf.gz")},
        "bcftools_stats": {"vcf": str(ENGINE_WORKSPACE / "input.vcf.gz"), "output": str(ENGINE_WORKSPACE / "bcftools.stats.txt")},
        "tabix_vcf": {"vcf_gz": str(ENGINE_WORKSPACE / "input.vcf.gz")},
        "mafft_align": {"fasta": str(ENGINE_WORKSPACE / "sequences.fasta"), "output": str(ENGINE_WORKSPACE / "aligned.fasta"), "threads": 2},
        "iqtree_build": {"alignment": str(ENGINE_WORKSPACE / "aligned.fasta"), "prefix": str(ENGINE_WORKSPACE / "iqtree_run"), "bootstrap": 1000, "threads": 2},
        "plink2_pca": {"pfile_prefix": str(ENGINE_WORKSPACE / "cohort"), "output_prefix": str(ENGINE_WORKSPACE / "plink_pca"), "pcs": 10, "threads": 2},
        "vina_dock": {"receptor": str(ENGINE_WORKSPACE / "receptor.pdbqt"), "ligand": str(ENGINE_WORKSPACE / "ligand.pdbqt"), "output": str(ENGINE_WORKSPACE / "docked.pdbqt"), "center_x": 0, "center_y": 0, "center_z": 0, "size_x": 20, "size_y": 20, "size_z": 20, "threads": 2},
        "gromacs_mdrun": {"tpr": str(ENGINE_WORKSPACE / "topol.tpr"), "deffnm": str(ENGINE_WORKSPACE / "md"), "threads": 2},
        "cellpose_segment": {"image": str(ENGINE_WORKSPACE / "image.tif"), "model": "cyto3", "diameter": 0},
        "openms_fileinfo": {"mzml": str(ENGINE_WORKSPACE / "sample.mzML"), "output": str(ENGINE_WORKSPACE / "openms_fileinfo.txt")},
    }
    parameter_json = st.text_area(
        "Plan parameters (JSON)",
        value=json.dumps(examples.get(selected_plan, {"threads": 2}), indent=2),
        height=240,
        key=f"step111_plan_parameters_{selected_plan}",
    )
    confirm = st.checkbox("I understand that this invokes an external local scientific engine when queued", key=f"step111_engine_confirm_{selected_plan}")
    plan = None
    if st.button("Validate plan", key=f"step111_validate_plan_{selected_plan}"):
        try:
            parameters = json.loads(parameter_json or "{}")
            plan = build_engine_plan(selected_plan, workdir=ENGINE_WORKSPACE, **parameters)
            st.session_state["step111_validated_plan"] = plan
            st.session_state["step111_validated_plan_key"] = selected_plan
            st.success("Plan validated without executing the engine.")
        except Exception as exc:
            st.error(f"Plan validation failed: {type(exc).__name__}: {exc}")
    plan = st.session_state.get("step111_validated_plan") if st.session_state.get("step111_validated_plan_key") == selected_plan else None
    if plan is not None:
        st.code(json.dumps(plan_to_dict(plan), indent=2, default=str), language="json")
        if st.button("Queue validated engine plan", type="primary", disabled=not confirm, key=f"step111_queue_engine_{selected_plan}"):
            queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
            raw_parameters = json.loads(parameter_json or "{}")
            job = queue.submit(
                "native_engine_execute",
                {
                    "plan_key": selected_plan,
                    "workdir": str(ENGINE_WORKSPACE),
                    "parameters": raw_parameters,
                    "timeout_seconds": 3600,
                    "stdout_to_output": selected_plan == "mafft_align",
                },
                priority=60,
                max_attempts=1,
                stages=["plan", "execute", "validate", "finalize"],
                resources={"threads": int(raw_parameters.get("threads", 2)), "external_engine": True},
            )
            st.success(f"External engine job queued: {job.job_id}")

with tabs[2]:
    st.subheader("Standard statistical disclosure")
    st.caption("Every analytical chart now receives a compact automatic footer. This workspace generates a full two-group disclosure with assumptions, effect size, confidence interval, missingness and reproducibility metadata.")
    stats_upload = st.file_uploader("Upload CSV/TSV/Excel for a two-group analysis", type=["csv", "tsv", "xlsx", "xls"], key="step111_stats_upload")
    stats_upload_profile = render_upload_preflight(
        stats_upload,
        key="step111_stats_upload",
        allowed_extensions=["csv", "tsv", "xlsx", "xls"],
        soft_limit_mb=25,
        hard_limit_mb=100,
    )
    if stats_upload is not None and stats_upload_profile is not None:
        frame = _read_table(stats_upload)
        numeric = frame.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric:
            for column in frame.columns:
                converted = pd.to_numeric(frame[column], errors="coerce")
                if converted.notna().sum() >= 2:
                    frame[column] = converted
            numeric = frame.select_dtypes(include=[np.number]).columns.tolist()
        categorical = [column for column in frame.columns if column not in numeric]
        if not numeric or not categorical:
            st.error("The file needs at least one numeric value column and one grouping column.")
        else:
            c1, c2 = st.columns(2)
            value_column = c1.selectbox("Numeric value", numeric)
            group_column = c2.selectbox("Group", categorical)
            groups = frame[group_column].dropna().astype(str).unique().tolist()
            if len(groups) >= 2:
                c3, c4 = st.columns(2)
                group_a = c3.selectbox("Group A", groups, index=0)
                group_b = c4.selectbox("Group B", [group for group in groups if group != group_a], index=0)
                biological_candidates = ["None"] + frame.columns.astype(str).tolist()
                biological = st.selectbox("Biological replicate ID (optional)", biological_candidates)
                technical = st.selectbox("Technical replicate ID (optional)", biological_candidates, key="step111_technical")
                if st.button("Generate statistical disclosure", type="primary", key="step111_disclosure"):
                    disclosure = two_group_disclosure(
                        frame,
                        value_column=value_column,
                        group_column=group_column,
                        group_a=group_a,
                        group_b=group_b,
                        biological_id_column=None if biological == "None" else biological,
                        technical_id_column=None if technical == "None" else technical,
                    )
                    st.session_state["step111_disclosure_result"] = disclosure
            disclosure = st.session_state.get("step111_disclosure_result")
            if disclosure is not None:
                smart_dataframe(disclosure.to_frame(), height=620, key="step111_disclosure_table")
                st.download_button("Download disclosure JSON", json.dumps(disclosure.to_dict(), indent=2), file_name="statistical_disclosure.json", mime="application/json")
                for warning in disclosure.warnings:
                    st.warning(warning)
                ci = bootstrap_confidence_interval(frame[value_column], iterations=1000)
                st.caption(f"Bootstrap mean 95% CI for the selected value column: {ci[0]} to {ci[1]}")

    with st.expander("Multiple-testing correction calculator", expanded=False):
        p_text = st.text_area("P-values, separated by commas", "0.001, 0.02, 0.04, 0.2")
        try:
            p_values = [float(token.strip()) for token in p_text.split(",") if token.strip()]
            corrected = benjamini_hochberg(p_values)
            smart_dataframe(pd.DataFrame({"p_value": p_values, "BH_adjusted": corrected}), key="step111_bh")
        except Exception as exc:
            st.warning(f"Enter valid p-values: {exc}")

with tabs[3]:
    st.subheader("Advanced viewer synchronization")
    store = ViewerSyncStore(ROOT / "reports" / "viewer_sync.sqlite3")
    project = active_project_key()
    st.caption(f"Active project context: {project}")
    history = store.history(project, limit=500)
    states = store.states(project, limit=500)
    metric_cards([
        ("Selection events", len(history), "Cross-view linked selections"),
        ("Saved viewer states", len(states), "Persistent state snapshots"),
        ("Project context", project, "Shared across modules"),
        ("Storage", "SQLite", "Durable local history"),
    ])
    if history.empty:
        st.info("Select records in an advanced scientific viewer to create synchronized selection events.")
    else:
        scientific_table(history, key="step111_sync_history", file_name="viewer_selection_history.csv", height=420)
    if not states.empty:
        scientific_table(states, key="step111_sync_states", file_name="viewer_state_snapshots.csv", height=360)

with tabs[4]:
    st.subheader("Scientific quality improvements")
    checklist = pd.DataFrame([
        {"Control": "Native-vs-proxy separation", "Status": "Implemented", "Evidence": "Native parser and external-engine result states are explicit"},
        {"Control": "Bounded memory", "Status": "Implemented", "Evidence": "100 MB interactive threshold; larger files use protected staging"},
        {"Control": "Provenance", "Status": "Implemented", "Evidence": "SHA-256, parser/engine identity, record counts and warnings"},
        {"Control": "Statistical disclosure", "Status": "Implemented", "Evidence": "Sample size, missingness, effect size, CI, assumptions and data hash"},
        {"Control": "Cross-view synchronization", "Status": "Implemented", "Evidence": "Selection events and state snapshots linked by project"},
        {"Control": "Safe engine execution", "Status": "Implemented", "Evidence": "Argument-list execution, protected workspace, timeout and checksums"},
        {"Control": "Clinical/regulatory interpretation", "Status": "External boundary", "Evidence": "Requires validated methods and independent specialist review"},
    ])
    scientific_table(checklist, key="step111_quality_checklist", file_name="step111_quality_controls.csv", selectable=False, height=420)
    st.info("Native format support and external engine integration improve scientific depth, but they do not manufacture independent validation, wet-lab evidence, regulatory acceptance or vendor certification.")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='real_engine_native_formats', title='Real Engine & Native Format Integration', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
