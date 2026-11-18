from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import zipfile

import pandas as pd
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe
from biointel.ui.operational_canvas import render_operational_canvas
from biointel.ui.workbench import compact_module_header

from .catalog import MODULE_BY_KEY
from .io import read_upload
from .scientific import AnalysisBundle, analyse_module, demo_frame, validate_frame
from .visuals import build_visuals
from .tools import readiness


_UPLOAD_TYPES = [
    "csv", "tsv", "txt", "json", "xlsx", "xls", "vcf", "vcf.gz", "bed", "bedpe",
    "narrowpeak", "broadpeak", "gff", "gff3", "gtf", "maf", "maf.gz",
]


def _frame_sha(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
    return sha256(payload).hexdigest()


def _evidence_zip(module_key: str, source: pd.DataFrame, bundle: AnalysisBundle, parameters: dict[str, object]) -> bytes:
    module = MODULE_BY_KEY[module_key]
    manifest = {
        "schema": "biointel.bioinformatics_peak.bundle.v137",
        "module": module_key,
        "title": module.title,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": _frame_sha(source),
        "input_rows": len(source),
        "parameters": parameters,
        "summary": bundle.summary,
        "scientific_boundary": module.boundary,
        "handoffs": list(module.handoffs),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        archive.writestr("result.csv", bundle.result.to_csv(index=False))
        archive.writestr("quality_gates.csv", bundle.quality.to_csv(index=False))
        for name, frame in bundle.extras.items():
            archive.writestr(f"tables/{name}.csv", frame.head(250_000).to_csv(index=False))
        archive.writestr("README.txt", f"{module.title}\n\n{module.boundary}\n")
    return buffer.getvalue()


def _column_mapping(frame: pd.DataFrame, required: tuple[str, ...], key_prefix: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    columns = list(map(str, frame.columns))
    missing = [column for column in required if column not in columns]
    if not missing:
        return frame
    st.markdown("#### Column mapping")
    st.caption("Map required scientific fields before running. A source column can be used only once.")
    mapping: dict[str, str] = {}
    available = ["— Not mapped —", *columns]
    used: set[str] = set()
    mapping_columns = st.columns(min(3, max(1, len(missing))))
    for index, target in enumerate(missing):
        choice = mapping_columns[index % len(mapping_columns)].selectbox(
            target,
            available,
            key=f"{key_prefix}_map_{target}",
        )
        if choice != "— Not mapped —":
            if choice in used:
                st.error(f"{choice} is mapped more than once. Choose a unique source column.")
            else:
                mapping[target] = choice
                used.add(choice)
    mapped = frame.copy()
    for target, source in mapping.items():
        mapped[target] = mapped[source]
    return mapped


def _render_quality(audit: dict[str, object]) -> None:
    metric_cards([
        ("Rows", f"{int(audit['rows']):,}", "Rows available for interactive analysis"),
        ("Columns", int(audit["columns"]), "Detected source fields"),
        ("Missing cells", f"{int(audit['missing_cells']):,}", "Missing values remain visible"),
        ("Duplicate rows", f"{int(audit['duplicate_rows']):,}", "Duplicates are not silently removed"),
    ])
    for warning in audit["warnings"]:
        st.warning(str(warning))


def _result_interpretation(bundle: AnalysisBundle, module_key: str) -> None:
    module = MODULE_BY_KEY[module_key]
    metrics = dict(bundle.summary.get("metrics", {}))
    priority = pd.to_numeric(bundle.result.get("priority_score", pd.Series(dtype=float)), errors="coerce")
    high = int((priority >= 0.7).sum()) if len(priority) else 0
    confidence = "Moderate" if high and bundle.quality["status"].eq("Block").sum() == 0 else "Limited"
    st.markdown("### Scientific interpretation")
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**Main finding**")
        st.write(f"The workflow produced {len(bundle.result):,} reviewable records; {high:,} meet the default high-priority threshold.")
        st.markdown("**Confidence**")
        st.write(confidence)
        st.markdown("**Observed metrics**")
        render_operational_canvas(
            "Observed scientific metrics",
            metrics,
            workflow=("Input", "Quality checks", "Analysis", "Review"),
        )
    with columns[1]:
        st.markdown("**Limitations**")
        st.write(module.boundary)
        st.markdown("**Recommended next step**")
        st.write("Review the top candidates, inspect underlying records, confirm data provenance and validate findings in an independent specialist workflow.")
        st.markdown("**Cross-module handoffs**")
        st.write(" · ".join(module.handoffs))


def _render_visuals(bundle: AnalysisBundle, module_key: str, key_prefix: str) -> None:
    artifacts = build_visuals(module_key, bundle)
    labels = [artifact.title for artifact in artifacts]
    selected = st.selectbox("Select scientific visual", labels, key=f"{key_prefix}_visual")
    artifact = artifacts[labels.index(selected)]
    st.plotly_chart(artifact.figure, width="stretch", key=f"{key_prefix}_plot_{labels.index(selected)}")
    st.caption(artifact.interpretation)
    with st.expander("Method, source table and underlying data", expanded=False):
        st.write(artifact.method)
        st.caption(f"Source: {artifact.source_name} · {len(artifact.data):,} bounded records")
        smart_dataframe(artifact.data.head(5000), height=360, key=f"{key_prefix}_visual_data")
        st.download_button(
            "Download visual data CSV",
            artifact.data.to_csv(index=False).encode("utf-8"),
            file_name=f"{module_key}_{labels.index(selected)+1:02d}_visual_data.csv",
            mime="text/csv",
            key=f"{key_prefix}_visual_download",
        )


def render_bioinformatics_peak_module(module_key: str, *, embedded: bool = False) -> None:
    module = MODULE_BY_KEY[module_key]
    key_prefix = f"biopeak137_{module_key}"
    if embedded:
        with st.expander(f"Bioinformatics Peak Expansion · {module.short_title}", expanded=False):
            st.caption("Advanced specialist workflow, eight signature visuals, evidence export and cross-module handoff.")
            _render_workspace(module_key, key_prefix, compact=True)
        return
    compact_module_header(
        title=module.title,
        summary=module.summary,
        icon="DNA",
        category=module.category,
        tags=("Specialist workflow", "8 scientific visuals", "Evidence export"),
        boundary=module.boundary,
    )
    _render_workspace(module_key, key_prefix, compact=False)


def _render_workspace(module_key: str, key_prefix: str, *, compact: bool) -> None:
    module = MODULE_BY_KEY[module_key]
    tabs = st.tabs(["1 · Input & QC", "2 · Results", "3 · Visual intelligence", "4 · Evidence & export", "5 · Guide"])
    source_state = f"{key_prefix}_source"
    bundle_state = f"{key_prefix}_bundle"
    params_state = f"{key_prefix}_parameters"

    with tabs[0]:
        mode = st.radio("Data source", ["Deterministic demonstration data", "Upload scientific data"], horizontal=True, key=f"{key_prefix}_mode")
        frame = pd.DataFrame()
        if mode == "Deterministic demonstration data":
            size = st.slider("Demonstration records", 120, 1200, 360 if not compact else 240, 60, key=f"{key_prefix}_demo_size")
            frame = demo_frame(module, size)
            st.info("Demonstration data is clearly labelled and is not external validation evidence.")
        else:
            upload = st.file_uploader("Upload data", type=_UPLOAD_TYPES, key=f"{key_prefix}_upload")
            if upload is not None:
                try:
                    frame = read_upload(upload, module_key)
                    st.success(f"Imported {len(frame):,} records from {upload.name}.")
                except Exception as exc:
                    st.error(f"Input failed safely · BIOINPUT-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                    st.write(str(exc))
        if not frame.empty:
            frame = _column_mapping(frame, module.required_columns, key_prefix)
            audit = validate_frame(frame, module)
            _render_quality(audit)
            with st.expander("Preview input records", expanded=not compact):
                smart_dataframe(frame.head(1000), height=350, key=f"{key_prefix}_preview")
            with st.form(f"{key_prefix}_run_form"):
                threshold = st.slider("Priority review threshold", 0.0, 1.0, 0.70, 0.05)
                retain_missing = st.checkbox("Retain incomplete records for review", value=True)
                run = st.form_submit_button("Run specialist analysis", type="primary")
            if run:
                try:
                    working = frame if retain_missing else frame.dropna(subset=list(module.required_columns))
                    with st.spinner("Running bounded specialist analysis…"):
                        bundle = analyse_module(working, module, threshold)
                    st.session_state[source_state] = working
                    st.session_state[bundle_state] = bundle
                    st.session_state[params_state] = {"threshold": threshold, "retain_missing": retain_missing}
                    st.success("Analysis completed. Results, visuals and evidence package are ready.")
                except Exception as exc:
                    error_id = sha256(f"{module_key}:{exc}".encode()).hexdigest()[:12].upper()
                    st.error(f"Analysis stopped safely · BIO-{error_id}")
                    st.write(str(exc))
        else:
            st.info("Select demonstration data or upload a supported scientific file to begin.")

    bundle = st.session_state.get(bundle_state)
    source = st.session_state.get(source_state)
    parameters = st.session_state.get(params_state, {})

    with tabs[1]:
        if not isinstance(bundle, AnalysisBundle):
            st.info("Run the analysis in Input & QC to populate results.")
        else:
            metrics = dict(bundle.summary.get("metrics", {}))
            metric_cards([(str(k).replace("_", " ").title(), v, None) for k, v in list(metrics.items())[:8]])
            smart_dataframe(bundle.result.head(25_000), height=520, key=f"{key_prefix}_results")
            _result_interpretation(bundle, module_key)
            with st.expander("Quality gates", expanded=False):
                smart_dataframe(bundle.quality, height=300, key=f"{key_prefix}_quality")

    with tabs[2]:
        if not isinstance(bundle, AnalysisBundle):
            st.info("Run the analysis to activate eight domain-specific scientific visuals.")
        else:
            _render_visuals(bundle, module_key, key_prefix)

    with tabs[3]:
        if not isinstance(bundle, AnalysisBundle) or not isinstance(source, pd.DataFrame):
            st.info("Run the analysis to create reproducible exports.")
        else:
            st.markdown("### Reproducible exports")
            st.download_button("Download result CSV", bundle.result.to_csv(index=False).encode("utf-8"), file_name=f"{module_key}_results.csv", mime="text/csv", key=f"{key_prefix}_result_csv")
            st.download_button("Download summary JSON", json.dumps(bundle.summary, indent=2, default=str).encode("utf-8"), file_name=f"{module_key}_summary.json", mime="application/json", key=f"{key_prefix}_summary_json")
            if st.button("Prepare evidence ZIP", key=f"{key_prefix}_prepare_zip"):
                st.session_state[f"{key_prefix}_zip"] = _evidence_zip(module_key, source, bundle, parameters)
            package = st.session_state.get(f"{key_prefix}_zip")
            if isinstance(package, bytes):
                st.download_button("Download evidence ZIP", package, file_name=f"{module_key}_evidence_bundle.zip", mime="application/zip", key=f"{key_prefix}_zip_download")
            st.markdown("### Handoff destinations")
            st.write(" · ".join(module.handoffs))
            if st.button("Save current result as active BioIntel dataset", key=f"{key_prefix}_handoff"):
                st.session_state["biointel_active_dataset"] = {
                    "name": f"{module.short_title} result",
                    "module": module_key,
                    "rows": len(bundle.result),
                    "sha256": _frame_sha(bundle.result),
                }
                st.success("Active dataset context updated for compatible downstream modules.")

    with tabs[4]:
        st.markdown("### Purpose")
        st.write(module.purpose)
        st.markdown("### Accepted inputs")
        st.write(" · ".join(module.accepted_inputs))
        st.markdown("### Workflow")
        for index, step in enumerate(module.workflow, start=1):
            st.write(f"{index}. {step}")
        st.markdown("### Outputs")
        st.write(" · ".join(module.outputs))
        st.markdown("### Visual coverage")
        st.write(" · ".join(module.visuals))
        st.markdown("### Specialist engine readiness")
        tool_rows = pd.DataFrame(readiness(module_key))
        smart_dataframe(tool_rows, height=320, key=f"{key_prefix}_tools")
        st.caption("Missing optional engines do not crash the module. The built-in transparent analysis remains available and external-engine claims are never fabricated.")
        st.warning(module.boundary)
