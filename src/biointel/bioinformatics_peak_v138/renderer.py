from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe
from biointel.ui.workbench import compact_module_header

from .catalog import MODULE_BY_KEY
from .io import read_upload
from .scientific import AnalysisBundle, analyse_module, demo_frame, validate_frame
from .visuals import build_visuals
from .tools import readiness
from .contracts import ParameterSpec, contract_for, parameters_for
from .background import stage_and_submit
from .comparison import compare_frames
from .engine_queue import clear_engine_readiness_cache, compatible_auto_plans, engine_readiness_rows, preview_engine_plan, submit_engine_run
from .native_profiles import profile_for, streamlit_upload_types
from .native_runtime import NativeInputBundle, prepare_native_input
from .publication import build_publication_bundle
from .reference_registry import ReferenceRegistry
from .review_store import REVIEW_STATUSES, ReviewStore
from .benchmark_center import BENCHMARK_PROFILES, BenchmarkStore, run_benchmark
from .consensus import build_consensus
from .execution_peak import CheckpointStore, diagnose_failure, plan_resources
from .harmonization import harmonize_samples
from .indexed_streaming import GenomicRegion, index_status, query_region
from .interoperability import standards_bundle, validate_phenopacket
from .portable_workflows import default_plan, workflow_pack
from .result_versions import ResultVersionStore, VALID_STATES
from .reference_diff import compare_reference_releases
from .last_mile import LAST_MILE_PROFILES
from .uncertainty import uncertainty_table


_PROJECT_ROOT = Path(__file__).resolve().parents[3]


_UPLOAD_TYPES = [
    "csv", "tsv", "txt", "json", "xlsx", "xls", "vcf", "vcf.gz", "bed", "bedpe",
    "narrowpeak", "broadpeak", "gff", "gff3", "gtf", "maf", "maf.gz",
    "airr", "pvar", "psam", "bim", "fam", "zip", "h5ad", "h5mu", "pgen",
]


def _frame_sha(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
    return sha256(payload).hexdigest()


def _evidence_zip(module_key: str, source: pd.DataFrame, bundle: AnalysisBundle, parameters: dict[str, object]) -> bytes:
    module = MODULE_BY_KEY[module_key]
    manifest = {
        "schema": "biointel.bioinformatics_peak.bundle.v138",
        "module": module_key,
        "title": module.title,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": _frame_sha(source),
        "input_rows": len(source),
        "parameters": parameters,
        "summary": bundle.summary,
        "scientific_boundary": module.boundary,
        "handoffs": list(module.handoffs),
        "quality_status": bundle.summary.get("quality_status"),
        "reference_assets": bundle.summary.get("reference_assets", []),
        "specialist_engines": bundle.summary.get("specialist_engines", []),
        "output_sha256": _frame_sha(bundle.result),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        result_bytes = bundle.result.to_csv(index=False).encode("utf-8")
        quality_bytes = bundle.quality.to_csv(index=False).encode("utf-8")
        archive.writestr("result.csv", result_bytes)
        archive.writestr("quality_gates.csv", quality_bytes)
        table_index: list[dict[str, object]] = [
            {"path": "result.csv", "rows": len(bundle.result), "sha256": sha256(result_bytes).hexdigest()},
            {"path": "quality_gates.csv", "rows": len(bundle.quality), "sha256": sha256(quality_bytes).hexdigest()},
        ]
        for name, frame in bundle.extras.items():
            bounded = frame.head(250_000)
            payload = bounded.to_csv(index=False).encode("utf-8")
            path = f"tables/{name}.csv"
            archive.writestr(path, payload)
            archive.writestr(f"schemas/{name}.json", json.dumps({"columns": [{"name": str(c), "dtype": str(bounded[c].dtype)} for c in bounded.columns], "rows_exported": len(bounded), "rows_available": len(frame), "truncated": len(frame) > len(bounded)}, indent=2))
            table_index.append({"path": path, "rows": len(bounded), "rows_available": len(frame), "sha256": sha256(payload).hexdigest()})
        archive.writestr("table_index.json", json.dumps(table_index, indent=2))
        archive.writestr("tool_readiness.json", json.dumps(readiness(module_key), indent=2, default=str))
        archive.writestr("visual_catalogue.json", json.dumps([{"title": item.title, "source": item.source_name, "method": item.method, "interpretation": item.interpretation} for item in build_visuals(module_key, bundle)], indent=2))
        report_lines = [
            f"# {module.title}", "", f"Generated: {manifest['generated_at_utc']}", "",
            f"Quality status: {bundle.summary.get('quality_status', 'Review')}", "",
            "## Metrics", *[f"- {str(k).replace('_', ' ').title()}: {v}" for k, v in bundle.summary.get('metrics', {}).items()], "",
            "## Scientific boundary", module.boundary, "", "## Handoffs", *[f"- {item}" for item in module.handoffs],
        ]
        archive.writestr("summary_report.md", "\n".join(map(str, report_lines)))
        archive.writestr("README.txt", f"{module.title}\n\nBuilt-in analysis is transparent and bounded.\nScientific boundary: {module.boundary}\n")
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
    threshold = float(bundle.summary.get("threshold", bundle.summary.get("parameters", {}).get("priority_threshold", 0.70)))
    high = int((priority >= threshold).sum()) if len(priority) else 0
    blocked = bundle.quality["status"].astype(str).str.lower().eq("block").any()
    review = bundle.quality["status"].astype(str).str.lower().eq("review").any()
    confidence = "Limited" if blocked else ("Moderate" if review else "High for research-use execution")
    st.markdown("### Scientific interpretation")
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**Main finding**")
        st.write(f"The workflow produced {len(bundle.result):,} reviewable records; {high:,} meet the configured priority threshold of {threshold:.2f}.")
        st.markdown("**Confidence**")
        st.write(confidence)
        st.markdown("**Observed metrics**")
        if metrics:
            metric_cards([(str(k).replace("_", " ").title(), v, None) for k, v in list(metrics.items())[:8]])
        else:
            st.write("No summary metrics were produced.")
    with columns[1]:
        st.markdown("**Limitations**")
        st.write(module.boundary)
        st.markdown("**Recommended next step**")
        st.write("Review the top candidates, inspect underlying records, confirm data provenance and validate findings in an independent specialist workflow.")
        st.markdown("**Cross-module handoffs**")
        st.write(" · ".join(module.handoffs))


def _visual_group(title: str) -> str:
    lower = title.lower()
    if any(token in lower for token in ("qc", "quality", "depth", "coverage", "balance", "dropout", "ambiguity")):
        return "QC"
    if any(token in lower for token in ("comparison", "concordance", "agreement", "population", "subgroup", "species", "batch", "shared", "longitudinal")):
        return "Comparison"
    if any(token in lower for token in ("evidence", "confidence", "review", "risk", "conflict", "provenance", "access", "consent")):
        return "Evidence"
    if any(token in lower for token in ("network", "sankey", "circos", "synteny", "trajectory", "topology", "fine-mapping", "regulatory", "recombination")):
        return "Advanced analysis"
    if any(token in lower for token in ("dashboard", "distribution", "summary", "composition", "profile")):
        return "Overview"
    return "Primary analysis"


def _render_visuals(bundle: AnalysisBundle, module_key: str, key_prefix: str) -> None:
    artifacts = build_visuals(module_key, bundle)
    grouped: dict[str, list[object]] = {}
    for artifact in artifacts:
        grouped.setdefault(_visual_group(artifact.title), []).append(artifact)
    ordered_groups = [group for group in ("Overview", "QC", "Primary analysis", "Advanced analysis", "Evidence", "Comparison") if group in grouped]
    group = st.radio("Visual workspace", ordered_groups, horizontal=True, key=f"{key_prefix}_visual_group")
    candidates = grouped[group]
    labels = [artifact.title for artifact in candidates]
    selected = st.selectbox("Select scientific visual", labels, key=f"{key_prefix}_visual")
    artifact = candidates[labels.index(selected)]
    st.markdown(f"### {artifact.title}")
    st.write(artifact.interpretation)
    metadata_cols = st.columns(4)
    metadata_cols[0].metric("Records", f"{len(artifact.data):,}")
    metadata_cols[1].metric("Source", artifact.source_name)
    metadata_cols[2].metric("Quality", str(bundle.summary.get("quality_status", "Review")))
    metadata_cols[3].metric("Evidence", "Research use")
    st.plotly_chart(artifact.figure, width="stretch", key=f"{key_prefix}_plot_{group}_{labels.index(selected)}")
    with st.expander("Method, source table and underlying data", expanded=False):
        st.write(artifact.method)
        st.caption(f"Source: {artifact.source_name} · {len(artifact.data):,} bounded records")
        smart_dataframe(artifact.data.head(5000), height=360, key=f"{key_prefix}_visual_data_{group}")
        download_cols = st.columns(3)
        visual_index = artifacts.index(artifact)
        download_cols[0].download_button(
            "Download visual data CSV",
            artifact.data.to_csv(index=False).encode("utf-8"),
            file_name=f"{module_key}_{visual_index+1:02d}_visual_data.csv",
            mime="text/csv",
            key=f"{key_prefix}_visual_download_{group}",
        )
        download_cols[1].download_button(
            "Download interactive HTML",
            artifact.figure.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"),
            file_name=f"{module_key}_{visual_index+1:02d}_visual.html",
            mime="text/html",
            key=f"{key_prefix}_visual_html_{group}",
        )
        download_cols[2].download_button(
            "Download Plotly JSON",
            artifact.figure.to_json().encode("utf-8"),
            file_name=f"{module_key}_{visual_index+1:02d}_visual.json",
            mime="application/json",
            key=f"{key_prefix}_visual_json_{group}",
        )

    with st.expander("Scientific inspection drawer", expanded=False):
        inspection = artifact.data.head(5000).reset_index(drop=True)
        if inspection.empty:
            st.info("This visual has no record-level data to inspect.")
        else:
            label_columns = [column for column in ("variant", "event_id", "gene", "sample", "cell", "clonotype", "species", "region", "feature_id") if column in inspection.columns]
            labels = []
            for index, row in inspection.iterrows():
                parts = [str(row[column]) for column in label_columns[:3] if str(row[column]).strip()]
                labels.append(f"{index + 1:,} · {' | '.join(parts) if parts else 'record'}")
            selected_label = st.selectbox("Inspect record", labels, key=f"{key_prefix}_inspection_{group}")
            selected_index = labels.index(selected_label)
            selected_record = inspection.iloc[selected_index].to_frame("Value")
            smart_dataframe(selected_record.reset_index(names="Field"), height=420, key=f"{key_prefix}_inspection_table_{group}")
            st.caption("The selected record can be reviewed, exported or handed off without changing the complete result table.")
            st.download_button("Download selected record JSON", json.dumps(inspection.iloc[selected_index].to_dict(), indent=2, default=str).encode("utf-8"), file_name=f"{module_key}_selected_record.json", mime="application/json", key=f"{key_prefix}_inspection_download_{group}")


def _parameter_widget(spec: ParameterSpec, key_prefix: str):
    key = f"{key_prefix}_param_{spec.key}"
    if spec.kind == "select":
        options = list(spec.options) or [str(spec.default)]
        index = options.index(spec.default) if spec.default in options else 0
        return st.selectbox(spec.label, options, index=index, help=spec.help, key=key)
    if spec.kind == "text":
        return st.text_input(spec.label, value=str(spec.default), help=spec.help, key=key)
    if spec.kind == "int":
        kwargs = {"value": int(spec.default), "step": int(spec.step or 1), "help": spec.help, "key": key}
        if spec.minimum is not None: kwargs["min_value"] = int(spec.minimum)
        if spec.maximum is not None: kwargs["max_value"] = int(spec.maximum)
        return st.number_input(spec.label, **kwargs)
    if spec.kind == "float":
        kwargs = {"value": float(spec.default), "step": float(spec.step or 0.01), "help": spec.help, "key": key, "format": "%.6g"}
        if spec.minimum is not None: kwargs["min_value"] = float(spec.minimum)
        if spec.maximum is not None: kwargs["max_value"] = float(spec.maximum)
        return st.number_input(spec.label, **kwargs)
    return spec.default


def _render_configuration(module_key: str, key_prefix: str, expert: bool) -> dict[str, object]:
    contract = contract_for(module_key)
    st.markdown("#### Scientific configuration")
    st.caption("Reference context and thresholds are saved in the reproducibility bundle.")
    specs = parameters_for(module_key, expert=expert)
    params: dict[str, object] = {}
    columns = st.columns(2)
    for index, spec in enumerate(specs):
        with columns[index % 2]:
            params[spec.key] = _parameter_widget(spec, key_prefix)
    if not expert:
        for spec in contract.parameters:
            if spec.advanced:
                params[spec.key] = spec.default
    return params


def _template_frame(module_key: str) -> pd.DataFrame:
    module = MODULE_BY_KEY[module_key]
    rows = []
    for index in range(3):
        row = {column: f"example_{column}_{index+1}" for column in module.required_columns}
        rows.append(row)
    return pd.DataFrame(rows)


def _execution_plan(rows: int, columns: int) -> tuple[str, str]:
    cells = rows * max(1, columns)
    if rows > 250_000 or cells > 20_000_000:
        return "Background recommended", "Large input: use staged parsing and background execution with resumable outputs."
    if rows > 50_000 or cells > 5_000_000:
        return "Bounded interactive", "Interactive analysis will use deterministic bounds; full input remains in the evidence manifest."
    return "Interactive", "Input is suitable for the local interactive engine."


def render_bioinformatics_peak_module(module_key: str, *, embedded: bool = False) -> None:
    module = MODULE_BY_KEY[module_key]
    key_prefix = f"biopeak138_{module_key}"
    if embedded:
        with st.expander(f"Bioinformatics Peak Expansion · {module.short_title}", expanded=False):
            st.caption("Advanced specialist workflow with native data, verified engine plans, linked visuals, scientific review, comparison and reproducible export.")
            _render_workspace(module_key, key_prefix, compact=True)
        return
    compact_module_header(
        title=module.title,
        summary=module.summary,
        icon="DNA",
        category=module.category,
        tags=("Native scientific data", "12 linked visuals", "GA4GH + portable workflows"),
        boundary=module.boundary,
    )
    _render_workspace(module_key, key_prefix, compact=False)


def _filter_bundle(bundle: AnalysisBundle, module_key: str, key_prefix: str) -> AnalysisBundle:
    result = bundle.result.copy()
    profile = profile_for(module_key)
    category_candidates = [
        column for column in (*profile.comparison_identifiers, "sample", "group", "condition", "chrom", "gene", "species", "cluster", "lineage", "event_type")
        if column in result.columns and result[column].nunique(dropna=True) <= 200
    ]
    with st.expander("Linked visual filters", expanded=False):
        category = st.selectbox("Filter field", ["No categorical filter", *dict.fromkeys(category_candidates)], key=f"{key_prefix}_linked_field")
        selected_values: list[str] = []
        if category != "No categorical filter":
            options = sorted(result[category].dropna().astype(str).unique().tolist())[:500]
            selected_values = st.multiselect("Included values", options, default=options[: min(len(options), 20)], key=f"{key_prefix}_linked_values")
            if selected_values:
                result = result[result[category].astype(str).isin(selected_values)]
        priority_range: tuple[float, float] | None = None
        if "priority_score" in result.columns:
            numeric = pd.to_numeric(result["priority_score"], errors="coerce").dropna()
            if len(numeric) and float(numeric.min()) < float(numeric.max()):
                priority_range = st.slider(
                    "Priority-score range",
                    min_value=float(numeric.min()), max_value=float(numeric.max()),
                    value=(float(numeric.min()), float(numeric.max())), key=f"{key_prefix}_linked_priority",
                )
                result = result[pd.to_numeric(result["priority_score"], errors="coerce").between(*priority_range)]
        st.caption(f"Linked selection contains {len(result):,} of {len(bundle.result):,} result records.")

    extras: dict[str, pd.DataFrame] = {}
    for name, table in bundle.extras.items():
        if not isinstance(table, pd.DataFrame):
            continue
        filtered = table.copy()
        if category_candidates and category != "No categorical filter" and category in filtered.columns and selected_values:
            filtered = filtered[filtered[category].astype(str).isin(selected_values)]
        if priority_range and "priority_score" in filtered.columns:
            filtered = filtered[pd.to_numeric(filtered["priority_score"], errors="coerce").between(*priority_range)]
        extras[name] = filtered
    summary = dict(bundle.summary)
    summary["linked_filter_rows"] = len(result)
    return AnalysisBundle(result=result, summary=summary, extras=extras, quality=bundle.quality)


def _record_key(frame: pd.DataFrame, index: int, module_key: str) -> tuple[str, dict[str, object]]:
    profile = profile_for(module_key)
    row = frame.iloc[int(index)].to_dict()
    parts = [str(row.get(column, "")) for column in profile.comparison_identifiers if column in row and str(row.get(column, "")).strip()]
    return (" | ".join(parts) or f"row-{index + 1}"), row


def _render_review_and_comparison(
    bundle: AnalysisBundle,
    source: pd.DataFrame,
    parameters: dict[str, object],
    module_key: str,
    key_prefix: str,
) -> None:
    store = ReviewStore(_PROJECT_ROOT)
    profile = profile_for(module_key)
    st.markdown("### Run snapshots and comparison")
    snapshot_cols = st.columns([1, 2])
    if snapshot_cols[0].button("Save current run snapshot", key=f"{key_prefix}_save_snapshot"):
        try:
            snapshot = store.save_snapshot(
                module_key=module_key,
                input_sha256=_frame_sha(source),
                result=bundle.result,
                summary=bundle.summary,
                parameters=parameters,
            )
            st.session_state[f"{key_prefix}_run_id"] = snapshot.run_id
            st.success(f"Saved {snapshot.run_id} with checksum-bound results.")
        except Exception as exc:
            st.error(f"Snapshot failed safely · BIOSNAP-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
            st.write(str(exc))

    snapshots = store.list_snapshots(module_key)
    if snapshots:
        labels = {f"{item.created_at_utc} · {item.row_count:,} rows · {item.run_id}": item for item in snapshots}
        selected_label = snapshot_cols[1].selectbox("Compare current result with", list(labels), key=f"{key_prefix}_compare_snapshot")
        selected_snapshot = labels[selected_label]
        if st.button("Run comparison", key=f"{key_prefix}_compare_button"):
            try:
                previous = store.load_snapshot_frame(selected_snapshot.run_id)
                comparison = compare_frames(bundle.result, previous, identifier_candidates=profile.comparison_identifiers)
                st.session_state[f"{key_prefix}_comparison"] = comparison
            except Exception as exc:
                st.error(f"Comparison failed safely · BIOCOMP-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                st.write(str(exc))
    else:
        st.info("Save at least one run snapshot to enable cohort, parameter and version comparison.")

    comparison = st.session_state.get(f"{key_prefix}_comparison")
    if comparison is not None:
        metric_cards([
            ("Added", comparison.summary.get("added_records", 0), None),
            ("Removed", comparison.summary.get("removed_records", 0), None),
            ("Changed", comparison.summary.get("changed_records", 0), None),
            ("Overlap", comparison.summary.get("overlap_records", 0), None),
        ])
        smart_dataframe(comparison.metric_changes, height=320, key=f"{key_prefix}_comparison_metrics")
        if not comparison.record_changes.empty:
            smart_dataframe(comparison.record_changes, height=380, key=f"{key_prefix}_comparison_records")

    st.markdown("### Scientific review queue")
    bounded = bundle.result.head(5000).reset_index(drop=True)
    if bounded.empty:
        st.info("No records are available for review.")
        return
    labels: dict[str, int] = {}
    for index in range(len(bounded)):
        record_label, _ = _record_key(bounded, index, module_key)
        unique = f"{index + 1:,} · {record_label[:140]}"
        labels[unique] = index
    selected_record_label = st.selectbox("Record", list(labels), key=f"{key_prefix}_review_record")
    selected_index = labels[selected_record_label]
    record_key, record = _record_key(bounded, selected_index, module_key)
    current_run_id = st.session_state.get(f"{key_prefix}_run_id")
    with st.form(f"{key_prefix}_review_form"):
        review_cols = st.columns(2)
        status = review_cols[0].selectbox("Decision", REVIEW_STATUSES, key=f"{key_prefix}_review_status")
        reviewer = review_cols[1].text_input("Reviewer", value="Local scientific reviewer", key=f"{key_prefix}_reviewer")
        reason = st.text_input("Decision reason", placeholder="State the scientific reason for this decision", key=f"{key_prefix}_review_reason")
        note = st.text_area("Review note", placeholder="Evidence, limitations, confirmation plan or escalation details", key=f"{key_prefix}_review_note")
        save_review = st.form_submit_button("Save review decision", type="primary")
    if save_review:
        try:
            store.upsert_decision(
                module_key=module_key, record_key=record_key, record=record, status=status,
                reason=reason, note=note, reviewer=reviewer, run_id=current_run_id,
            )
            st.success("Review decision saved to the persistent local audit queue.")
        except Exception as exc:
            st.error(f"Review save failed safely · BIOREV-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
            st.write(str(exc))
    summary = store.summary(module_key)
    metric_cards([(status_name, count, None) for status_name, count in summary.items()])
    decisions = store.decisions(module_key, limit=1000)
    if not decisions.empty:
        smart_dataframe(decisions.drop(columns=["record_json"], errors="ignore"), height=380, key=f"{key_prefix}_review_table")
        st.download_button("Download review queue", decisions.to_csv(index=False).encode("utf-8"), file_name=f"{module_key}_review_queue.csv", mime="text/csv", key=f"{key_prefix}_review_download")


def _render_native_and_engines(module_key: str, key_prefix: str, native_bundle: NativeInputBundle | None) -> None:
    profile = profile_for(module_key)
    st.markdown("### Native scientific formats")
    st.write(" · ".join(f".{item}" for item in profile.accepted_extensions))
    st.caption("Native inputs are staged atomically, checksum-verified and parsed with bounded readers. Binary assets are never unsafely deserialised.")
    if native_bundle is not None:
        summary = native_bundle.summary()
        metric_cards([
            ("Format", summary["native"].get("format", "Unknown"), None),
            ("Size", f"{int(summary['native'].get('size_bytes', 0)) / (1024 * 1024):.2f} MB", None),
            ("Preview records", f"{int(summary['native'].get('records_loaded', 0)):,}", None),
            ("Analysis ready", "Yes" if native_bundle.analysis_ready else "No", None),
        ])
        if native_bundle.blocking_reason:
            st.warning(native_bundle.blocking_reason)
        for warning in native_bundle.warnings:
            st.warning(warning)
        smart_dataframe(pd.DataFrame([summary["native"]]), height=230, key=f"{key_prefix}_native_summary")
        if not native_bundle.parse_result.primary.empty:
            with st.expander("Native primary preview", expanded=False):
                smart_dataframe(native_bundle.parse_result.primary.head(5000), height=360, key=f"{key_prefix}_native_primary")
        for name, table in native_bundle.parse_result.secondary.items():
            if isinstance(table, pd.DataFrame) and not table.empty:
                with st.expander(f"Native secondary table · {name}", expanded=False):
                    smart_dataframe(table.head(5000), height=330, key=f"{key_prefix}_native_secondary_{name}")
    else:
        st.info("Inspect a native scientific file in Input & QC to activate native previews and automatic engine plans.")

    st.markdown("### External specialist-engine readiness")
    if st.button("Refresh engine readiness", key=f"{key_prefix}_refresh_engines"):
        clear_engine_readiness_cache()
    try:
        engine_table = pd.DataFrame(engine_readiness_rows(module_key))
        smart_dataframe(engine_table, height=390, key=f"{key_prefix}_engine_status")
    except Exception as exc:
        st.error(f"Engine readiness probe failed safely · BIOENG-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
        st.write(str(exc))

    if native_bundle is not None:
        plans = compatible_auto_plans(module_key, native_bundle.staged_path)
        if plans:
            st.markdown("#### Protected automatic engine plans")
            plan_map = {plan.label: plan for plan in plans}
            selected_label = st.selectbox("Engine plan", list(plan_map), key=f"{key_prefix}_engine_plan")
            auto_plan = plan_map[selected_label]
            try:
                preview = preview_engine_plan(auto_plan, native_bundle.staged_path)
                st.code(" ".join(preview["plan"]["command"]), language="text")
                if preview["available"]:
                    st.success(f"{preview['engine_status']['label']} is available and the protected no-shell plan is valid.")
                else:
                    st.warning(f"{preview['engine_status']['label']} is not installed. The plan is shown but cannot be queued.")
                timeout = st.number_input("Engine timeout seconds", min_value=10, max_value=86400, value=3600, step=10, key=f"{key_prefix}_engine_timeout")
                if st.button("Queue verified engine plan", disabled=not bool(preview["available"]), key=f"{key_prefix}_queue_engine"):
                    record = submit_engine_run(_PROJECT_ROOT, auto_plan, native_bundle.staged_path, timeout_seconds=int(timeout))
                    st.session_state[f"{key_prefix}_engine_job"] = record.job_id
                    try:
                        from biointel.step101.background import BackgroundJobService
                        BackgroundJobService(_PROJECT_ROOT).start()
                    except Exception:
                        pass
                    st.success(f"Queued engine job {record.job_id}. Track it in Performance & Job Center.")
            except Exception as exc:
                st.error(f"Engine plan stopped safely · BIOPLAN-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                st.write(str(exc))
        else:
            st.info("No safe one-file automatic plan matches this native input. Readiness and reference requirements remain available for a manual specialist workflow.")

    st.markdown("### Versioned reference assets")
    registry = ReferenceRegistry(_PROJECT_ROOT)
    reference_table = registry.table(module_key)
    smart_dataframe(reference_table, height=360, key=f"{key_prefix}_reference_table")
    with st.expander("Bind or update a local reference asset", expanded=False):
        available = registry.available_assets(limit=5000)
        requirement = st.selectbox("Requirement", list(profile.reference_assets), key=f"{key_prefix}_reference_requirement")
        options = available["relative_path"].astype(str).tolist() if not available.empty else []
        relative = st.selectbox("File under data/reference_assets", options, key=f"{key_prefix}_reference_file") if options else st.text_input("Relative file path", key=f"{key_prefix}_reference_path")
        pin = st.checkbox("Pin SHA-256 checksum", value=True, key=f"{key_prefix}_reference_pin")
        bind_cols = st.columns(2)
        if bind_cols[0].button("Bind and verify", key=f"{key_prefix}_reference_bind"):
            try:
                registry.bind(module_key, requirement, relative, pin_checksum=pin)
                st.success("Reference asset bound. Rerun to refresh its verification state.")
            except Exception as exc:
                st.error(f"Reference binding failed safely · BIOREF-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                st.write(str(exc))
        if bind_cols[1].button("Remove binding", key=f"{key_prefix}_reference_unbind"):
            registry.unbind(module_key, requirement)
            st.success("Reference binding removed.")



def _render_peak_v140(
    module_key: str,
    key_prefix: str,
    bundle: AnalysisBundle | None,
    source: pd.DataFrame | None,
    parameters: dict[str, object],
    native_bundle: NativeInputBundle | None,
) -> None:
    st.markdown("### Standards, benchmarking and portable execution")
    st.caption("Canonical identifiers, portable workflow manifests, consensus, uncertainty, result versions and resource-aware execution are generated locally. No remote service or external validation is fabricated.")

    profile = profile_for(module_key)
    input_bytes = 0
    if native_bundle is not None:
        try:
            input_bytes = Path(native_bundle.staged_path).stat().st_size
        except Exception:
            input_bytes = 0
    rows = len(source) if isinstance(source, pd.DataFrame) else 0
    columns = len(source.columns) if isinstance(source, pd.DataFrame) else 0
    plan = plan_resources(input_bytes=input_bytes, rows=rows, columns=columns, engine_count=len(profile.engines), gpu_capable=module_key in {"single_cell_multiome", "gene_regulatory_network", "proteogenomics_peak"})
    metric_cards([
        ("Execution mode", plan.mode, plan.rationale),
        ("Estimated RAM", f"{plan.estimated_ram_gb:.2f} GB", None),
        ("Temporary disk", f"{plan.temporary_disk_gb:.2f} GB", None),
        ("CPU threads", plan.cpu_threads, f"Runtime: {plan.runtime_range}"),
    ])

    portable = default_plan(module_key, input_name=Path(native_bundle.staged_path).name if native_bundle else "analysis_input.csv")
    portable_payload = workflow_pack(portable)
    with st.expander("Portable WES / TES / TRS / DRS workflow pack", expanded=False):
        task_rows = []
        for task in portable.tasks:
            task_rows.append({
                "Task": task.task_id, "Name": task.name, "Dependencies": ", ".join(task.dependencies),
                "CPU": task.cpu_cores, "RAM GB": task.memory_gb, "Disk GB": task.disk_gb,
                "Container": task.container.image if task.container else "Native",
                "Digest": task.container.digest if task.container else "",
            })
        smart_dataframe(pd.DataFrame(task_rows), height=340, key=f"{key_prefix}_portable_tasks")
        st.download_button(
            "Download portable workflow pack JSON",
            json.dumps(portable_payload, indent=2, default=str).encode("utf-8"),
            file_name=f"{module_key}_portable_workflow_v140.json",
            mime="application/json",
            key=f"{key_prefix}_portable_download",
        )

    if native_bundle is not None:
        with st.expander("Indexed regional inspection", expanded=False):
            status = index_status(native_bundle.staged_path)
            st.write(status)
            region_text = st.text_input("Genomic region", value="chr1:1-100000", key=f"{key_prefix}_region")
            max_records = st.number_input("Maximum regional records", min_value=10, max_value=10000, value=1000, step=10, key=f"{key_prefix}_region_limit")
            if st.button("Inspect region", key=f"{key_prefix}_inspect_region"):
                try:
                    region = GenomicRegion.parse(region_text)
                    regional = query_region(native_bundle.staged_path, region, max_records=int(max_records))
                    st.session_state[f"{key_prefix}_regional"] = regional
                    st.success(f"Loaded {len(regional):,} bounded regional records.")
                except Exception as exc:
                    diagnostic = diagnose_failure(exc, stage="indexed-region-query")
                    st.error(f"Regional inspection stopped safely · {diagnostic['recovery_id']}")
                    st.write(diagnostic["recommended_fix"])
            regional = st.session_state.get(f"{key_prefix}_regional")
            if isinstance(regional, pd.DataFrame):
                smart_dataframe(regional, height=320, key=f"{key_prefix}_regional_table")

    if not isinstance(bundle, AnalysisBundle) or not isinstance(source, pd.DataFrame):
        st.info("Run the specialist analysis to activate standards, consensus, uncertainty, benchmark and result-version workflows.")
        return

    standards = standards_bundle(module_key, bundle.result)
    standard_summary = standards.get("variant_summary", {})
    standard_cols = st.columns(3)
    standard_cols[0].metric("Canonicalized variants", int(standard_summary.get("Canonicalized", 0)))
    standard_cols[1].metric("Variant records needing review", int(standard_summary.get("Review", 0)))
    standard_cols[2].metric("Portable workflow tasks", len(portable.tasks))
    st.download_button(
        "Download GA4GH-compatible interoperability bundle",
        json.dumps(standards, indent=2, default=str).encode("utf-8"),
        file_name=f"{module_key}_interoperability_v140.json",
        mime="application/json",
        key=f"{key_prefix}_standards_download",
    )
    if standards.get("variant_records"):
        with st.expander("Canonical VRS-style variant identifiers", expanded=False):
            smart_dataframe(pd.DataFrame(standards["variant_records"]).head(25000), height=360, key=f"{key_prefix}_vrs_table")

    if module_key == "federated_genomic_discovery":
        with st.expander("Phenopacket structural validation", expanded=False):
            phenopacket_text = st.text_area("Phenopacket JSON", value='{"id":"example","subject":{"id":"subject-1"},"phenotypicFeatures":[{"type":{"id":"HP:0001250"}}],"metaData":{"createdBy":"BioIntel AI"}}', height=180, key=f"{key_prefix}_phenopacket")
            if st.button("Validate Phenopacket", key=f"{key_prefix}_validate_phenopacket"):
                try:
                    issues = validate_phenopacket(json.loads(phenopacket_text))
                    issue_table = pd.DataFrame([item.__dict__ for item in issues])
                    if issue_table.empty:
                        st.success("No structural validation issues detected by the local compatibility validator.")
                    else:
                        smart_dataframe(issue_table, height=280, key=f"{key_prefix}_phenopacket_issues")
                except Exception as exc:
                    diagnostic = diagnose_failure(exc, stage="phenopacket-validation")
                    st.error(f"Phenopacket validation stopped safely · {diagnostic['recovery_id']}")

    st.markdown("#### Multi-engine consensus and uncertainty")
    caller_candidates = [column for column in ("caller", "method", "engine", "source", "tool") if column in bundle.result.columns]
    if caller_candidates:
        consensus_cols = st.columns([2, 1])
        caller_column = consensus_cols[0].selectbox("Caller/method column", caller_candidates, key=f"{key_prefix}_caller_column")
        minimum_callers = consensus_cols[1].number_input("Minimum callers", min_value=1, max_value=10, value=2, key=f"{key_prefix}_minimum_callers")
        if st.button("Build consensus", key=f"{key_prefix}_build_consensus"):
            try:
                consensus = build_consensus(bundle.result, caller_column=caller_column, minimum_callers=int(minimum_callers))
                st.session_state[f"{key_prefix}_consensus"] = consensus
            except Exception as exc:
                diagnostic = diagnose_failure(exc, stage="consensus")
                st.error(f"Consensus stopped safely · {diagnostic['recovery_id']}")
                st.write(diagnostic["recommended_fix"])
        consensus = st.session_state.get(f"{key_prefix}_consensus")
        if consensus is not None:
            metric_cards([
                ("Consensus events", len(consensus.consensus), None),
                ("Unique/review events", len(consensus.unique_calls), None),
                ("Callers", len(consensus.caller_summary), None),
            ])
            smart_dataframe(consensus.consensus.head(25000), height=360, key=f"{key_prefix}_consensus_table")
            with st.expander("Caller agreement matrix", expanded=False):
                smart_dataframe(consensus.agreement_matrix, height=320, key=f"{key_prefix}_agreement_matrix")
    else:
        st.info("A caller/method/source column activates multi-engine consensus. Current result remains single-method and is not presented as consensus.")

    if st.button("Estimate bootstrap uncertainty", key=f"{key_prefix}_uncertainty"):
        try:
            table, summary = uncertainty_table(bundle.result, iterations=500)
            st.session_state[f"{key_prefix}_uncertainty_table"] = table
            st.session_state[f"{key_prefix}_uncertainty_summary"] = summary
        except Exception as exc:
            diagnostic = diagnose_failure(exc, stage="uncertainty")
            st.error(f"Uncertainty analysis stopped safely · {diagnostic['recovery_id']}")
    uncertainty = st.session_state.get(f"{key_prefix}_uncertainty_table")
    if isinstance(uncertainty, pd.DataFrame):
        smart_dataframe(uncertainty, height=330, key=f"{key_prefix}_uncertainty_table_view")

    st.markdown("#### Sample and cohort harmonization")
    harmonized = harmonize_samples([source, bundle.result])
    metric_cards([
        ("Unique samples", harmonized.summary.get("unique_samples", 0), None),
        ("Shared across sources", harmonized.summary.get("samples_shared_across_sources", 0), None),
        ("Missing sample IDs", harmonized.summary.get("missing_sample_ids", 0), None),
    ])
    with st.expander("Harmonization audit", expanded=False):
        smart_dataframe(harmonized.audit, height=260, key=f"{key_prefix}_harmonization_audit")
        smart_dataframe(harmonized.sample_map.head(25000), height=320, key=f"{key_prefix}_sample_map")

    st.markdown("#### Gold-standard benchmark center")
    profile_row = BENCHMARK_PROFILES[module_key]
    st.write(f"**Benchmark profile:** {profile_row.name}")
    st.caption(f"Truth: {'; '.join(profile_row.truth_requirements)} · External reference: {profile_row.external_reference}")
    columns = list(bundle.result.columns)
    benchmark_cols = st.columns(3)
    truth_column = benchmark_cols[0].selectbox("Truth column", ["—", *columns], key=f"{key_prefix}_truth_column")
    prediction_column = benchmark_cols[1].selectbox("Prediction/score column", ["—", *columns], key=f"{key_prefix}_prediction_column")
    subgroup_options = [column for column in columns if bundle.result[column].nunique(dropna=True) <= 200]
    subgroup_column = benchmark_cols[2].selectbox("Optional subgroup", ["—", *subgroup_options], key=f"{key_prefix}_benchmark_subgroup")
    if st.button("Run benchmark", key=f"{key_prefix}_run_benchmark"):
        if truth_column == "—" or prediction_column == "—":
            st.warning("Select explicit truth and prediction columns. BioIntel will not invent benchmark truth.")
        else:
            try:
                table, summary = run_benchmark(bundle.result, truth_column=truth_column, prediction_column=prediction_column, module_key=module_key, subgroup_column=None if subgroup_column == "—" else subgroup_column)
                run_id = BenchmarkStore(_PROJECT_ROOT).save(module_key, summary)
                st.session_state[f"{key_prefix}_benchmark_table"] = table
                st.success(f"Benchmark run {run_id} saved with explicit truth/prediction fields.")
            except Exception as exc:
                diagnostic = diagnose_failure(exc, stage="benchmark")
                st.error(f"Benchmark stopped safely · {diagnostic['recovery_id']}")
                st.write(diagnostic["recommended_fix"])
    benchmark_table = st.session_state.get(f"{key_prefix}_benchmark_table")
    if isinstance(benchmark_table, pd.DataFrame):
        smart_dataframe(benchmark_table, height=330, key=f"{key_prefix}_benchmark_results")
    history = BenchmarkStore(_PROJECT_ROOT).history(module_key)
    if not history.empty:
        with st.expander("Benchmark history", expanded=False):
            smart_dataframe(history, height=300, key=f"{key_prefix}_benchmark_history")

    with st.expander("Reference release difference viewer", expanded=False):
        st.caption("Compare two CSV/TSV reference release exports. Added, removed and changed identifiers are reported; previous analyses are not silently reinterpreted.")
        old_release = st.file_uploader("Older reference release", type=["csv", "tsv", "txt"], key=f"{key_prefix}_old_reference_release")
        new_release = st.file_uploader("Newer reference release", type=["csv", "tsv", "txt"], key=f"{key_prefix}_new_reference_release")
        if old_release is not None and new_release is not None and st.button("Compare reference releases", key=f"{key_prefix}_compare_references"):
            try:
                old_sep = "\t" if old_release.name.lower().endswith((".tsv", ".txt")) else ","
                new_sep = "\t" if new_release.name.lower().endswith((".tsv", ".txt")) else ","
                old_frame = pd.read_csv(old_release, sep=old_sep, nrows=250000)
                new_frame = pd.read_csv(new_release, sep=new_sep, nrows=250000)
                release_diff = compare_reference_releases(old_frame, new_frame)
                st.session_state[f"{key_prefix}_reference_diff"] = release_diff
            except Exception as exc:
                diagnostic = diagnose_failure(exc, stage="reference-release-diff")
                st.error(f"Reference comparison stopped safely · {diagnostic['recovery_id']}")
                st.write(diagnostic["recommended_fix"])
        release_diff = st.session_state.get(f"{key_prefix}_reference_diff")
        if release_diff is not None:
            metric_cards([(key.title(), value, None) for key, value in release_diff.summary.items() if key != "keys"])
            st.write(f"Identifier columns: {', '.join(release_diff.summary.get('keys', []))}")
            if not release_diff.changed.empty:
                smart_dataframe(release_diff.changed, height=300, key=f"{key_prefix}_reference_changed")
            if not release_diff.added.empty:
                smart_dataframe(release_diff.added.head(25000), height=260, key=f"{key_prefix}_reference_added")
            if not release_diff.removed.empty:
                smart_dataframe(release_diff.removed.head(25000), height=260, key=f"{key_prefix}_reference_removed")

    st.markdown("#### Scientific result versioning")
    version_store = ResultVersionStore(_PROJECT_ROOT)
    versions = version_store.list(module_key)
    version_cols = st.columns(3)
    version_state = version_cols[0].selectbox("Version state", VALID_STATES, key=f"{key_prefix}_version_state")
    reviewer = version_cols[1].text_input("Reviewer", value="Local scientific reviewer", key=f"{key_prefix}_version_reviewer")
    parent_options = ["None"] + (versions["version_id"].astype(str).tolist() if not versions.empty else [])
    parent = version_cols[2].selectbox("Parent version", parent_options, key=f"{key_prefix}_version_parent")
    reason = st.text_input("Version/change reason", key=f"{key_prefix}_version_reason")
    if st.button("Save result version", key=f"{key_prefix}_save_result_version"):
        try:
            record = version_store.save(module_key=module_key, frame=bundle.result, state=version_state, reason=reason, reviewer=reviewer, input_hash=_frame_sha(source), parent_version_id=None if parent == "None" else parent)
            st.success(f"Saved {record['version_id']} as {record['state']}.")
        except Exception as exc:
            diagnostic = diagnose_failure(exc, stage="result-versioning")
            st.error(f"Result version stopped safely · {diagnostic['recovery_id']}")
            st.write(diagnostic["recommended_fix"])
    versions = version_store.list(module_key)
    if not versions.empty:
        smart_dataframe(versions.drop(columns=["payload_path"], errors="ignore"), height=320, key=f"{key_prefix}_result_versions")

    st.markdown("#### Stage checkpoint compatibility")
    checkpoint_store = CheckpointStore(_PROJECT_ROOT)
    run_id = st.text_input("Checkpoint run ID", value=f"{module_key}-local", key=f"{key_prefix}_checkpoint_run_id")
    checkpoint_cols = st.columns(2)
    stage = checkpoint_cols[0].selectbox("Stage", ["verify", "parse", "analyse", "consensus", "benchmark", "export", "validate"], key=f"{key_prefix}_checkpoint_stage")
    if checkpoint_cols[1].button("Record completed checkpoint", key=f"{key_prefix}_record_checkpoint"):
        checkpoint_store.save(run_id=run_id, stage=stage, status="completed", input_hash=_frame_sha(source), parameters=parameters, output_hash=_frame_sha(bundle.result), payload={"module_key": module_key, "rows": len(bundle.result)})
        st.success("Checkpoint saved with input, parameter and output hashes.")
    resume = checkpoint_store.resume_state(run_id, input_hash=_frame_sha(source), parameters=parameters)
    if resume:
        smart_dataframe(pd.DataFrame(resume), height=300, key=f"{key_prefix}_checkpoint_table")

def _render_workspace(module_key: str, key_prefix: str, *, compact: bool) -> None:
    module = MODULE_BY_KEY[module_key]
    tabs = st.tabs([
        "1 · Input & QC", "2 · Results", "3 · Visual intelligence", "4 · Review & compare",
        "5 · Native & engines", "6 · Standards & validation", "7 · Evidence & export", "8 · Guide",
    ])
    source_state = f"{key_prefix}_source"
    bundle_state = f"{key_prefix}_bundle"
    params_state = f"{key_prefix}_parameters"
    source_hash_state = f"{key_prefix}_source_sha"
    native_state = f"{key_prefix}_native_bundle"

    with tabs[0]:
        template = _template_frame(module_key)
        template_cols = st.columns([1, 1, 2])
        template_cols[0].download_button("Input template CSV", template.to_csv(index=False).encode("utf-8"), file_name=f"{module_key}_input_template.csv", mime="text/csv", key=f"{key_prefix}_template")
        template_cols[1].download_button("Starter data CSV", demo_frame(module, 120).to_csv(index=False).encode("utf-8"), file_name=f"{module_key}_starter_data.csv", mime="text/csv", key=f"{key_prefix}_starter")
        mode = st.radio(
            "Data source",
            ["Deterministic demonstration data", "Upload analysis table", "Native scientific file"],
            horizontal=True, key=f"{key_prefix}_mode",
        )
        frame = pd.DataFrame()
        if mode == "Deterministic demonstration data":
            size = st.slider("Demonstration records", 120, 1200, 360 if not compact else 240, 60, key=f"{key_prefix}_demo_size")
            frame = demo_frame(module, size)
            st.info("Demonstration data is clearly labelled and is not external validation evidence.")
        elif mode == "Upload analysis table":
            upload = st.file_uploader("Upload analysis-ready data", type=_UPLOAD_TYPES, key=f"{key_prefix}_upload")
            if upload is not None:
                try:
                    frame = read_upload(upload, module_key)
                    st.success(f"Imported {len(frame):,} records from {upload.name}.")
                except Exception as exc:
                    st.error(f"Input failed safely · BIOINPUT-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                    st.write(str(exc))
        else:
            native_upload = st.file_uploader("Upload native scientific data", type=streamlit_upload_types(module_key), key=f"{key_prefix}_native_upload")
            if native_upload is not None:
                signature = f"{native_upload.name}:{getattr(native_upload, 'size', len(native_upload.getvalue()))}"
                if st.session_state.get(f"{key_prefix}_native_signature") != signature:
                    st.session_state.pop(native_state, None)
                    st.session_state[f"{key_prefix}_native_signature"] = signature
                if st.button("Inspect and checksum native file", type="primary", key=f"{key_prefix}_inspect_native"):
                    try:
                        with st.spinner("Staging and inspecting the native scientific file…"):
                            native_bundle = prepare_native_input(_PROJECT_ROOT, native_upload, module_key=module_key)
                        st.session_state[native_state] = native_bundle
                        st.success("Native file staged atomically and inspected with bounded parsing.")
                    except Exception as exc:
                        st.error(f"Native input stopped safely · BIONATIVE-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                        st.write(str(exc))
            native_bundle = st.session_state.get(native_state)
            if isinstance(native_bundle, NativeInputBundle):
                frame = native_bundle.analysis_frame.copy()
                metric_cards([
                    ("Format", native_bundle.parse_result.format_key, None),
                    ("Native records", f"{native_bundle.parse_result.record_count:,}", None),
                    ("Analysis ready", "Yes" if native_bundle.analysis_ready else "No", None),
                    ("SHA-256", native_bundle.parse_result.sha256[:12] + "…", None),
                ])
                if not native_bundle.analysis_ready:
                    st.warning(native_bundle.blocking_reason)

        if not frame.empty:
            frame = _column_mapping(frame, module.required_columns, key_prefix)
            audit = validate_frame(frame, module)
            _render_quality(audit)
            with st.expander("Preview input records", expanded=not compact):
                smart_dataframe(frame.head(1000), height=350, key=f"{key_prefix}_preview")
            execution_mode, execution_detail = _execution_plan(len(frame), len(frame.columns))
            st.info(f"Execution mode · {execution_mode} — {execution_detail}")
            experience = st.radio("Workspace mode", ["Guided", "Expert"], horizontal=True, key=f"{key_prefix}_experience")
            with st.form(f"{key_prefix}_run_form"):
                parameters = _render_configuration(module_key, key_prefix, expert=experience == "Expert")
                retain_missing = st.checkbox("Retain incomplete records for review", value=True, help="Incomplete rows remain traceable instead of being silently removed.")
                run = st.form_submit_button("Run specialist analysis", type="primary")
            if run:
                try:
                    missing_policy = str(parameters.get("missing_policy", "Retain and flag"))
                    keep_missing = retain_missing and missing_policy != "Exclude incomplete records"
                    working = frame if keep_missing else frame.dropna(subset=list(module.required_columns))
                    threshold = float(parameters.get("priority_threshold", 0.70))
                    with st.spinner("Running deep bounded specialist analysis…"):
                        bundle = analyse_module(working, module, threshold, parameters=parameters)
                    st.session_state[source_state] = working
                    st.session_state[bundle_state] = bundle
                    st.session_state[source_hash_state] = _frame_sha(working)
                    st.session_state[params_state] = {**parameters, "retain_missing": keep_missing, "workspace_mode": experience}
                    for transient in (f"{key_prefix}_zip", f"{key_prefix}_publication", f"{key_prefix}_comparison"):
                        st.session_state.pop(transient, None)
                    st.success("Analysis completed. Deep QC, linked visuals, review workflow and evidence packages are ready.")
                except Exception as exc:
                    error_id = sha256(f"{module_key}:{exc}".encode()).hexdigest()[:12].upper()
                    st.error(f"Analysis stopped safely · BIO-{error_id}")
                    st.write(str(exc))
        else:
            st.info("Select demonstration data, upload an analysis table or inspect a supported native scientific file to begin.")

    bundle = st.session_state.get(bundle_state)
    source = st.session_state.get(source_state)
    parameters = st.session_state.get(params_state, {})
    native_bundle = st.session_state.get(native_state)
    if not isinstance(native_bundle, NativeInputBundle):
        native_bundle = None

    with tabs[1]:
        if not isinstance(bundle, AnalysisBundle):
            st.info("Run the analysis in Input & QC to populate results.")
        else:
            metrics = dict(bundle.summary.get("metrics", {}))
            metric_cards([(str(k).replace("_", " ").title(), v, None) for k, v in list(metrics.items())[:8]])
            status = str(bundle.summary.get("quality_status", "Review"))
            if status == "Blocked": st.error("Quality status: Blocked — resolve blocker rows before downstream use.")
            elif status == "Review": st.warning("Quality status: Review — findings require inspection.")
            else: st.success("Quality status: Passed for research-use analysis.")
            smart_dataframe(bundle.result.head(25_000), height=520, key=f"{key_prefix}_results")
            with st.expander("Derived scientific tables", expanded=False):
                table_names = [name for name, table in bundle.extras.items() if isinstance(table, pd.DataFrame)]
                selected_table = st.selectbox("Derived table", table_names, key=f"{key_prefix}_derived_table") if table_names else None
                if selected_table:
                    table = bundle.extras[selected_table]
                    smart_dataframe(table.head(25_000), height=420, key=f"{key_prefix}_derived_table_view")
                    st.download_button("Download derived table", table.to_csv(index=False).encode("utf-8"), file_name=f"{module_key}_{selected_table}.csv", mime="text/csv", key=f"{key_prefix}_derived_download")
            _result_interpretation(bundle, module_key)
            with st.expander("Quality gates", expanded=False):
                smart_dataframe(bundle.quality, height=300, key=f"{key_prefix}_quality")

    with tabs[2]:
        if not isinstance(bundle, AnalysisBundle):
            st.info("Run the analysis to activate twelve linked domain-specific scientific visuals.")
        else:
            filtered_bundle = _filter_bundle(bundle, module_key, key_prefix)
            _render_visuals(filtered_bundle, module_key, key_prefix)

    with tabs[3]:
        if not isinstance(bundle, AnalysisBundle) or not isinstance(source, pd.DataFrame):
            st.info("Run the analysis to activate persistent scientific review and run comparison.")
        else:
            _render_review_and_comparison(bundle, source, parameters, module_key, key_prefix)

    with tabs[4]:
        _render_native_and_engines(module_key, key_prefix, native_bundle)

    with tabs[5]:
        _render_peak_v140(module_key, key_prefix, bundle if isinstance(bundle, AnalysisBundle) else None, source if isinstance(source, pd.DataFrame) else None, parameters, native_bundle)

    with tabs[6]:
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

            st.markdown("### Publication-grade figure package")
            include_static = st.checkbox("Attempt SVG, 300-DPI PNG and PDF export when Kaleido is installed", value=False, key=f"{key_prefix}_static_export")
            if st.button("Prepare publication package", key=f"{key_prefix}_prepare_publication"):
                try:
                    registry = ReferenceRegistry(_PROJECT_ROOT)
                    review_store = ReviewStore(_PROJECT_ROOT)
                    st.session_state[f"{key_prefix}_publication"] = build_publication_bundle(
                        module_key=module_key, source=source, bundle=bundle, visuals=build_visuals(module_key, bundle),
                        parameters=parameters, reference_status=registry.table(module_key).to_dict("records"),
                        review_summary=review_store.summary(module_key), include_static=include_static,
                    )
                except Exception as exc:
                    st.error(f"Publication package failed safely · BIOPUB-{sha256(str(exc).encode()).hexdigest()[:10].upper()}")
                    st.write(str(exc))
            publication = st.session_state.get(f"{key_prefix}_publication")
            if isinstance(publication, bytes):
                st.download_button("Download publication package", publication, file_name=f"{module_key}_publication_bundle.zip", mime="application/zip", key=f"{key_prefix}_publication_download")

            st.markdown("### Background reproducibility run")
            st.caption("Stages the current scientific table in protected UserData, submits a resumable local job and starts the existing BioIntel background worker when available.")
            background_cols = st.columns([1, 2])
            if background_cols[0].button("Queue background run", key=f"{key_prefix}_background"):
                try:
                    submission = stage_and_submit(_PROJECT_ROOT, source, module_key=module_key, parameters=parameters)
                    job_id = str(submission["job"]["job_id"])
                    st.session_state[f"{key_prefix}_background_job"] = job_id
                    try:
                        from biointel.step101.background import BackgroundJobService
                        BackgroundJobService(_PROJECT_ROOT).start()
                        worker_message = "Background worker started or already running."
                    except Exception as worker_exc:
                        worker_message = f"Job queued. Start the worker from Performance & Job Center if needed ({worker_exc})."
                    st.success(f"Queued {job_id}. {worker_message}")
                except Exception as exc:
                    error_id = sha256(f"background:{module_key}:{exc}".encode()).hexdigest()[:12].upper()
                    st.error(f"Background staging stopped safely · BIOJOB-{error_id}")
                    st.write(str(exc))
            job_id = st.session_state.get(f"{key_prefix}_background_job")
            if job_id:
                background_cols[1].info(f"Latest queued job: {job_id} · Track, pause, resume or cancel it in Performance & Job Center.")

            st.markdown("### Cross-module handoff")
            destination = st.selectbox("Destination", list(module.handoffs), key=f"{key_prefix}_handoff_destination")
            handoff_limit = st.number_input("Records to hand off", min_value=1, max_value=max(1, min(25_000, len(bundle.result))), value=max(1, min(500, len(bundle.result))), step=1, key=f"{key_prefix}_handoff_limit")
            handoff_payload = {
                "schema": "biointel.module_handoff.v3", "source_module": module_key, "source_title": module.title,
                "destination": destination, "records": int(handoff_limit), "result_sha256": _frame_sha(bundle.result),
                "parameters": parameters, "scientific_boundary": module.boundary,
                "reference_status": ReferenceRegistry(_PROJECT_ROOT).table(module_key).to_dict("records"),
            }
            handoff_cols = st.columns(2)
            if handoff_cols[0].button("Save active dataset and handoff", key=f"{key_prefix}_handoff"):
                st.session_state["biointel_active_dataset"] = {
                    "name": f"{module.short_title} result", "module": module_key, "rows": len(bundle.result),
                    "sha256": _frame_sha(bundle.result), "data": bundle.result.head(int(handoff_limit)).copy(),
                }
                queue = list(st.session_state.get("biointel_handoff_queue", []))
                queue.append(handoff_payload)
                st.session_state["biointel_handoff_queue"] = queue[-50:]
                st.success(f"Active dataset prepared for {destination}.")
            handoff_cols[1].download_button("Download handoff manifest", json.dumps(handoff_payload, indent=2, default=str).encode("utf-8"), file_name=f"{module_key}_to_{destination.lower().replace(' ', '_')}_handoff.json", mime="application/json", key=f"{key_prefix}_handoff_manifest")

    with tabs[7]:
        st.markdown("### Purpose")
        st.write(module.purpose)
        st.markdown("### Accepted analysis inputs")
        st.write(" · ".join(module.accepted_inputs))
        profile = profile_for(module_key)
        st.markdown("### Native scientific inputs")
        st.write(" · ".join(f".{item}" for item in profile.accepted_extensions))
        st.markdown("### Native and peak features")
        st.write(" · ".join(profile.native_features))
        st.markdown("### Workflow")
        for index, step in enumerate(module.workflow, start=1):
            st.write(f"{index}. {step}")
        st.markdown("### Outputs")
        st.write(" · ".join(module.outputs))
        st.markdown("### Visual coverage")
        st.write(" · ".join(module.visuals))
        contract = contract_for(module_key)
        st.markdown("### Deep feature coverage")
        st.write(" · ".join(contract.capabilities))
        st.markdown("### Last-mile peak features")
        st.write(" · ".join(LAST_MILE_PROFILES[module_key].features))
        st.caption("Specialist confirmation: " + " · ".join(LAST_MILE_PROFILES[module_key].specialist_confirmations))
        st.markdown("### Quality-control coverage")
        st.write(" · ".join(contract.qc_checks))
        st.markdown("### Required/versioned references")
        st.write(" · ".join(profile.reference_assets))
        st.markdown("### Scientific review roles")
        st.write(" · ".join(contract.review_roles))
        st.markdown("### Specialist engine readiness")
        tool_rows = pd.DataFrame(readiness(module_key))
        smart_dataframe(tool_rows, height=320, key=f"{key_prefix}_tools")
        st.caption("Missing optional engines do not crash the module. Built-in transparent analysis remains available and external-engine claims are never fabricated.")
        st.warning(module.boundary)
