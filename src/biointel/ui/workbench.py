from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import html
import io
import json
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

try:  # Core validators remain importable in CLI/API test environments.
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - UI runtime supplies Streamlit.
    st = None  # type: ignore[assignment]

from biointel.jobs.local_queue import LocalJobQueue
try:
    from biointel.ui.components import scientific_table, smart_dataframe, smart_json
except ModuleNotFoundError:  # pragma: no cover - only non-UI helpers are available.
    scientific_table = smart_dataframe = smart_json = None  # type: ignore[assignment]

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
INTERACTIVE_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_INTERACTIVE_ROWS = 500_000
MAX_RESULT_ROWS = 250_000
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_FORMAT_GROUPS: tuple[tuple[str, set[str]], ...] = (
    ("Tables", {"csv", "tsv", "txt", "json", "xlsx", "xls", "ods"}),
    ("Genomics", {"fa", "fasta", "fna", "faa", "fas", "fastq", "fq", "vcf", "bed", "bedpe", "gff", "gff3", "gtf", "gz"}),
    ("Single-cell", {"h5ad", "loom", "mtx"}),
    ("Structures", {"pdb", "cif", "mmcif", "sdf", "mol", "mol2"}),
    ("Mass spectrometry", {"mzml", "mzxml", "mgf"}),
    ("Images", {"png", "jpg", "jpeg", "tif", "tiff", "ome.tif", "ome.tiff"}),
)

_THRESHOLD_LABELS: dict[str, str] = {
    "epigenomics_chromatin": "Regulatory-region evidence threshold",
    "metabolomics_lipidomics": "Metabolite prioritisation threshold",
    "immunoinformatics_vaccine": "Epitope evidence threshold",
    "antibody_biologics": "Developability acceptance threshold",
    "docking_dynamics": "Pose confidence threshold",
    "pharmacogenomics": "Evidence review threshold",
    "spatial_omics_pathology": "Spatial signal threshold",
    "single_cell_trajectory": "Trajectory evidence threshold",
    "bioimage_microscopy": "Object quality threshold",
    "biostatistics_design": "Design adequacy threshold",
    "clinical_trial_biomarker": "Biomarker evidence threshold",
    "genome_editing_safety": "Guide safety threshold",
    "proteogenomics_neoantigen": "Neoantigen evidence threshold",
    "bioprocess_fermentation": "Process quality threshold",
    "lims_eln_chain": "Record completeness threshold",
    "causal_biology": "Causal evidence threshold",
    "explainable_ai": "Model assurance threshold",
    "multiomics_harmonization": "Harmonisation quality threshold",
    "glycomics_glycoproteomics": "Glycoform evidence threshold",
    "one_health_environmental": "Surveillance alert threshold",
    "synthetic_data_privacy": "Privacy and utility threshold",
    "population_gwas": "Association review threshold",
    "structural_variant_repeat": "Variant evidence threshold",
    "longitudinal_multiomics": "Temporal evidence threshold",
    "rna_isoform_splicing": "Splicing evidence threshold",
    "epitranscriptomics": "RNA-modification evidence threshold",
    "strain_microbiome": "Strain evidence threshold",
    "cell_atlas_mapping": "Annotation confidence threshold",
    "phenotypic_screening": "Hit selection threshold",
    "organoid_3d": "Organoid phenotype threshold",
    "protein_language_design": "Sequence design threshold",
    "enzyme_pathway_design": "Enzyme/pathway evidence threshold",
    "host_pathogen_interaction": "Interaction evidence threshold",
    "virology_evolution": "Viral evolution review threshold",
    "rare_variant_family": "Family variant evidence threshold",
    "digital_pathology_foundation": "Tumour-region review threshold",
    "long_read_epigenome": "Differential methylation review threshold",
    "single_cell_long_read_isoforms": "Isoform support threshold",
    "biomedical_foundation_model_hub": "Model operational-readiness threshold",
    "amr_surveillance": "Resistance surveillance alert threshold",
    "spatial_medicine_tme": "Immune-exclusion review threshold",
    "gene_therapy_vector": "Vector safety and packaging threshold",
    "cell_therapy_cart": "CAR engineering acceptance threshold",
    "federated_biomedical_ai": "Federated utility and privacy threshold",
    "clinical_biomarker_survival": "Biomarker evidence threshold",
    "protein_ligand_codesign": "Co-design candidate threshold",
    "pangenome_population_medicine": "Population-specific evidence threshold",
    "pharmacovigilance_intelligence": "Safety-signal review threshold",
    "synthetic_cohort_trial": "Simulation balance threshold",
    "autonomous_lab_planner": "Experimental-design completeness threshold",
}


@dataclass(frozen=True)
class SourceSelection:
    mode: str
    upload: Any | None
    demo_size: int
    is_large_upload: bool
    staged_path: str = ""


@dataclass(frozen=True)
class RunState:
    signature: str
    result: pd.DataFrame
    summary: dict[str, Any]
    secondary: pd.DataFrame | None
    extras: dict[str, pd.DataFrame]
    parameters: dict[str, Any]
    completed_at_utc: str


def compact_module_header(
    *,
    title: str,
    summary: str,
    icon: str,
    category: str,
    tags: Iterable[str] = (),
    boundary: str | None = None,
) -> None:
    from biointel.ui.premium_visuals import svg_icon_html

    icon_html = svg_icon_html(
        title=title,
        category=category,
        hint=icon,
        size=34,
        css_class="bio-svg-icon bio-wb-header-svg",
    )
    tags_html = "".join(
        f'<span class="bio-wb-chip">{html.escape(str(tag))}</span>'
        for tag in list(tags)[:3]
    )
    st.markdown(
        f"""
        <section class="bio-wb-header">
          <div class="bio-wb-icon" aria-hidden="true">{icon_html}</div>
          <div class="bio-wb-heading">
            <div class="bio-wb-category">{html.escape(category)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(summary)}</p>
          </div>
          <div class="bio-wb-chips">{tags_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    if boundary:
        with st.expander("Evidence boundary and responsible-use note", expanded=False):
            st.warning(boundary)


def _group_extensions(extensions: Iterable[str]) -> list[tuple[str, list[str]]]:
    remaining = {str(ext).lower().lstrip(".") for ext in extensions}
    groups: list[tuple[str, list[str]]] = []
    for label, candidates in _FORMAT_GROUPS:
        matches = sorted(remaining.intersection(candidates))
        if matches:
            groups.append((label, matches))
            remaining.difference_update(matches)
    if remaining:
        groups.append(("Other", sorted(remaining)))
    return groups


def render_format_support(extensions: Iterable[str]) -> None:
    groups = _group_extensions(extensions)
    content = []
    for label, values in groups:
        chips = "".join(f'<span class="bio-wb-format">.{html.escape(value)}</span>' for value in values[:8])
        more = f'<span class="bio-wb-format-more">+{len(values) - 8}</span>' if len(values) > 8 else ""
        content.append(
            f'<div class="bio-wb-format-group"><b>{html.escape(label)}</b><span>{chips}{more}</span></div>'
        )
    st.markdown('<div class="bio-wb-formats">' + "".join(content) + "</div>", unsafe_allow_html=True)


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned[:120] or "scientific_upload.dat"


def stage_large_upload(upload: Any, *, module_key: str, project_root: Path) -> dict[str, Any]:
    user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or project_root / "UserData")
    directory = user_root / "staged_uploads" / module_key
    directory.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(str(getattr(upload, "name", "scientific_upload.dat")))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = directory / f"{stamp}-{safe}"
    digest = hashlib.sha256()
    total = 0
    if hasattr(upload, "seek"):
        upload.seek(0)
    with destination.open("wb") as handle:
        while True:
            chunk = upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                handle.close()
                destination.unlink(missing_ok=True)
                raise ValueError("The file exceeds the 1 GB per-file limit.")
            digest.update(chunk)
            handle.write(chunk)
    if hasattr(upload, "seek"):
        upload.seek(0)
    queue = LocalJobQueue(runtime_database_path(project_root, "jobs.sqlite3"))
    job = queue.submit(
        "scientific_large_file_inspect",
        {"path": str(destination), "module_key": module_key, "original_name": str(getattr(upload, "name", safe))},
        priority=80,
        max_attempts=2,
        stages=["verify_path", "stream_hash", "sample", "finalize"],
        resources={"memory_mb": 256, "io_bound": True},
        estimated_seconds=max(5.0, total / (40 * 1024 * 1024)),
    )
    manifest = {
        "module": module_key,
        "original_name": str(getattr(upload, "name", safe)),
        "staged_path": str(destination),
        "size_bytes": total,
        "sha256": digest.hexdigest(),
        "staged_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "queued_for_background_review",
        "job_id": job.job_id,
    }
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def render_source_selector(
    *,
    key: str,
    module_key: str,
    extensions: Iterable[str],
    required_columns: Iterable[str],
    project_root: Path,
    demo_min: int,
    demo_max: int,
    demo_default: int,
    demo_step: int,
) -> SourceSelection:
    source = st.radio(
        "Data source",
        ["Upload scientific data", "Use demonstration data"],
        horizontal=True,
        key=f"{key}_source",
    )
    upload = None
    demo_size = demo_default
    staged_path = ""
    is_large = False

    if source.startswith("Upload"):
        st.markdown("#### Upload data")
        render_format_support(extensions)
        upload = st.file_uploader(
            "Choose or drop a module-compatible file",
            type=list(extensions),
            key=f"{key}_upload",
            help="Maximum 1 GB per file. Files above 100 MB use staged background-safe handling.",
        )
        st.caption("1 GB maximum per file · files up to 100 MB can run interactively · larger files are staged to disk for background-safe review")
        if upload is not None:
            size = int(getattr(upload, "size", 0) or 0)
            if size > MAX_UPLOAD_BYTES:
                st.error("The selected file exceeds the 1 GB per-file limit.")
                upload = None
            elif size > INTERACTIVE_UPLOAD_BYTES:
                is_large = True
                st.warning(
                    f"Large-file mode: {size / 1024 / 1024:.1f} MB. Interactive parsing is disabled to prevent RAM spikes. Stage the file first.",
                    icon="🗄️",
                )
                if st.button("Stage file for background-safe review", type="primary", key=f"{key}_stage"):
                    try:
                        with st.spinner("Writing the upload to protected local staging storage..."):
                            manifest = stage_large_upload(upload, module_key=module_key, project_root=project_root)
                        st.session_state[f"{key}_staged_manifest"] = manifest
                        st.success("File staged successfully. Use the Background Job Center for long-running processing.")
                    except Exception as exc:
                        st.error(f"Staging failed safely: {exc}")
                manifest = st.session_state.get(f"{key}_staged_manifest")
                if isinstance(manifest, dict):
                    staged_path = str(manifest.get("staged_path", ""))
                    st.code(staged_path, language="text")
    else:
        st.markdown("#### Demonstration dataset")
        demo_size = st.slider(
            "Dataset scale",
            demo_min,
            demo_max,
            demo_default,
            demo_step,
            key=f"{key}_demo_size",
        )
        st.caption("Deterministic demonstration data are generated locally and are always labelled as non-release evidence.")

    with st.expander("Input template and required schema", expanded=False):
        required = [str(value) for value in required_columns]
        st.markdown("**Required table fields**")
        st.code(", ".join(required) if required else "No fixed table schema; the module inspects the selected file.", language="text")
        if required:
            template = pd.DataFrame(columns=required).to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV template",
                template,
                f"{module_key}_input_template.csv",
                "text/csv",
                key=f"{key}_template",
            )

    return SourceSelection(
        mode="upload" if source.startswith("Upload") else "demo",
        upload=upload,
        demo_size=demo_size,
        is_large_upload=is_large,
        staged_path=staged_path,
    )


def render_column_mapping(raw: pd.DataFrame, required_columns: Iterable[str], *, key: str) -> pd.DataFrame:
    if raw.empty:
        return raw
    required = [str(column) for column in required_columns]
    missing = [column for column in required if column not in raw.columns]
    if not missing:
        return raw
    st.warning(f"{len(missing)} required field(s) are not mapped yet: {', '.join(missing)}")
    mapped = raw.copy()
    used: set[str] = set()
    with st.expander("Map uploaded columns", expanded=True):
        st.caption("Each source column can be assigned once. Leave a field unmapped to keep it in the review queue.")
        for target in missing:
            options = ["— Not mapped —", *[str(column) for column in raw.columns if str(column) not in used]]
            selection = st.selectbox(
                f"{target}",
                options,
                key=f"{key}_map_{target}",
            )
            if selection != "— Not mapped —":
                used.add(selection)
                mapped[target] = raw[selection]
    return mapped


def _safe_duplicate_count(data: pd.DataFrame) -> int:
    if data.empty:
        return 0
    converted = data.copy()
    for column in converted.columns:
        if converted[column].dtype == "object":
            converted[column] = converted[column].map(
                lambda value: json.dumps(value, sort_keys=True, default=str)
                if isinstance(value, (dict, list, tuple, set))
                else value
            )
    return int(converted.duplicated().sum())


def render_data_readiness(data: pd.DataFrame, required_columns: Iterable[str], *, key: str) -> dict[str, Any]:
    required = [str(column) for column in required_columns]
    missing_required = [column for column in required if column not in data.columns]
    missing_cells = int(data.isna().sum().sum()) if not data.empty else 0
    duplicates = _safe_duplicate_count(data)
    status_rows = [
        {"Check": "File parsed", "Status": "Passed" if not data.empty else "Blocked", "Detail": f"{len(data):,} rows" if not data.empty else "No records available"},
        {"Check": "Required fields", "Status": "Passed" if not missing_required else "Review", "Detail": "All fields detected" if not missing_required else ", ".join(missing_required)},
        {"Check": "Missing values", "Status": "Passed" if missing_cells == 0 else "Review", "Detail": f"{missing_cells:,} missing cells"},
        {"Check": "Duplicate rows", "Status": "Passed" if duplicates == 0 else "Review", "Detail": f"{duplicates:,} exact duplicates"},
    ]
    # Keep the import summary compact. The previous four st.metric columns could
    # become extremely tall when an SVG/help-icon style leaked from an embedded
    # visual, pushing the actual records and scientific visuals far below the fold.
    summary_items = (
        ("Rows", f"{len(data):,}"),
        ("Columns", f"{len(data.columns):,}"),
        ("Missing cells", f"{missing_cells:,}"),
        ("Duplicates", f"{duplicates:,}"),
    )
    summary_html = "".join(
        f'<span><small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
        for label, value in summary_items
    )
    st.markdown(
        f'<div class="bio-readiness-inline" role="group" aria-label="Imported data summary">{summary_html}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("#### Data readiness")
    smart_dataframe(pd.DataFrame(status_rows), height=210, key=f"{key}_readiness")
    return {
        "rows": len(data),
        "columns": list(data.columns),
        "missing_cells": missing_cells,
        "duplicate_rows": duplicates,
        "missing_required": missing_required,
        "ready": bool(not data.empty and not missing_required),
    }


def render_analysis_controls(data: pd.DataFrame, *, module_key: str, key: str) -> dict[str, Any]:
    threshold = st.slider(
        _THRESHOLD_LABELS.get(module_key, "Evidence / prioritisation threshold"),
        0.30,
        0.95,
        0.70,
        0.05,
        key=f"{key}_threshold",
    )
    top_n = st.slider("Results to display", 10, 150, 40, 5, key=f"{key}_top_n")
    parameters: dict[str, Any] = {"threshold": threshold, "top_n": top_n}
    advanced = st.toggle("Advanced filters", value=False, key=f"{key}_advanced")
    if advanced and not data.empty:
        categorical = [
            column
            for column in data.columns
            if not pd.api.types.is_numeric_dtype(data[column]) and 1 < data[column].nunique(dropna=True) <= 40
        ]
        numeric = [column for column in data.columns if pd.api.types.is_numeric_dtype(data[column])]
        c1, c2 = st.columns(2)
        if categorical:
            category_column = c1.selectbox("Filter category", ["None", *categorical], key=f"{key}_category_column")
            if category_column != "None":
                values = sorted(data[category_column].dropna().astype(str).unique().tolist())
                selected = c1.multiselect("Included values", values, default=values, key=f"{key}_category_values")
                parameters["category_column"] = category_column
                parameters["category_values"] = selected
        if numeric:
            numeric_column = c2.selectbox("Numeric range", ["None", *numeric], key=f"{key}_numeric_column")
            if numeric_column != "None":
                values = pd.to_numeric(data[numeric_column], errors="coerce").dropna()
                if not values.empty:
                    minimum, maximum = float(values.min()), float(values.max())
                    if np.isfinite(minimum) and np.isfinite(maximum) and maximum > minimum:
                        selected_range = c2.slider(
                            f"{numeric_column.replace('_', ' ').title()} range",
                            minimum,
                            maximum,
                            (minimum, maximum),
                            key=f"{key}_numeric_range",
                        )
                        parameters["numeric_column"] = numeric_column
                        parameters["numeric_range"] = [float(selected_range[0]), float(selected_range[1])]
    return parameters


def apply_analysis_filters(data: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    filtered = data.copy()
    category = parameters.get("category_column")
    selected = parameters.get("category_values")
    if category in filtered.columns and selected is not None:
        filtered = filtered[filtered[category].astype(str).isin([str(value) for value in selected])]
    numeric = parameters.get("numeric_column")
    selected_range = parameters.get("numeric_range")
    if numeric in filtered.columns and isinstance(selected_range, (list, tuple)) and len(selected_range) == 2:
        values = pd.to_numeric(filtered[numeric], errors="coerce")
        filtered = filtered[values.between(float(selected_range[0]), float(selected_range[1]), inclusive="both")]
    return filtered


def data_signature(data: pd.DataFrame, parameters: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(str(data.shape).encode("utf-8"))
    digest.update("|".join(map(str, data.columns)).encode("utf-8"))
    digest.update("|".join(map(str, data.dtypes)).encode("utf-8"))
    if not data.empty:
        sample = pd.concat([data.head(250), data.tail(250)], ignore_index=True)
        for column in sample.columns:
            if sample[column].dtype == "object":
                sample[column] = sample[column].map(
                    lambda value: json.dumps(value, sort_keys=True, default=str)
                    if isinstance(value, (dict, list, tuple, set))
                    else str(value)
                )
        digest.update(pd.util.hash_pandas_object(sample, index=True).values.tobytes())
    digest.update(json.dumps(parameters, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def _safe_error_id(state_key: str, exc: BaseException) -> str:
    payload = f"{state_key}|{type(exc).__name__}|{str(exc)}".encode("utf-8", errors="replace")
    return "ERR-" + hashlib.sha256(payload).hexdigest()[:12].upper()


def _frame_memory_mb(frame: pd.DataFrame | None) -> float:
    if frame is None or not isinstance(frame, pd.DataFrame):
        return 0.0
    try:
        return float(frame.memory_usage(index=True, deep=True).sum()) / (1024 * 1024)
    except Exception:
        return 0.0


def _validate_analysis_outputs(
    result: pd.DataFrame,
    summary: dict[str, Any],
    secondary: pd.DataFrame | None,
    extras: dict[str, pd.DataFrame] | None,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]:
    if not isinstance(result, pd.DataFrame):
        raise TypeError("The analysis engine returned a non-tabular primary result")
    if result.columns.duplicated().any():
        duplicates = result.columns[result.columns.duplicated()].astype(str).tolist()
        raise ValueError(f"The primary result contains duplicate columns: {duplicates[:5]}")
    if len(result) > MAX_RESULT_ROWS:
        raise ValueError(f"The interactive result contains {len(result):,} rows; use the background-job export path above {MAX_RESULT_ROWS:,} rows")
    clean_result = result.replace([np.inf, -np.inf], np.nan)
    clean_secondary = secondary.replace([np.inf, -np.inf], np.nan) if isinstance(secondary, pd.DataFrame) else None
    clean_extras: dict[str, pd.DataFrame] = {}
    for name, table in (extras or {}).items():
        if table is None:
            continue
        if not isinstance(table, pd.DataFrame):
            raise TypeError(f"Advanced output {name!r} is not tabular")
        if table.columns.duplicated().any():
            raise ValueError(f"Advanced output {name!r} contains duplicate columns")
        clean_extras[str(name)] = table.replace([np.inf, -np.inf], np.nan).head(MAX_RESULT_ROWS)
    clean_summary = dict(summary or {})
    return clean_result, clean_summary, clean_secondary, clean_extras


def run_analysis_once(
    *,
    state_key: str,
    data: pd.DataFrame,
    parameters: dict[str, Any],
    analyser: Callable[[pd.DataFrame, float], tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]],
    module_key: str | None = None,
) -> RunState | None:
    filtered = apply_analysis_filters(data, parameters)
    if len(filtered) > MAX_INTERACTIVE_ROWS:
        st.error(
            f"Interactive analysis is capped at {MAX_INTERACTIVE_ROWS:,} rows to prevent RAM exhaustion. "
            "Use the staged background-job workflow for this dataset."
        )
        return None
    signature = data_signature(filtered, parameters)
    current = st.session_state.get(state_key)
    if isinstance(current, RunState) and current.signature != signature:
        st.info("Parameters or input data changed. Existing results are marked outdated until you run the analysis again.")
    run = st.button(
        "Run analysis",
        type="primary",
        width="stretch",
        disabled=filtered.empty,
        key=f"{state_key}_run",
    )
    if run:
        try:
            started = time.perf_counter()
            with st.status("Running bounded scientific analysis...", expanded=True) as status:
                status.write(f"Preparing {len(filtered):,} filtered record(s)")
                result, summary, secondary, extras = analyser(filtered, float(parameters["threshold"]))
                status.write("Validating output tables, finite values and evidence manifest")
                result, summary, secondary, extras = _validate_analysis_outputs(result, summary, secondary, extras)
                elapsed = time.perf_counter() - started
                summary = dict(summary)
                summary["runtime_seconds"] = round(elapsed, 4)
                summary["input_memory_mb"] = round(_frame_memory_mb(filtered), 3)
                summary["result_memory_mb"] = round(
                    _frame_memory_mb(result) + _frame_memory_mb(secondary) + sum(_frame_memory_mb(table) for table in extras.values()),
                    3,
                )
                summary["stability_profile"] = "step130_bounded_interactive_v2"
                completed_at = datetime.now(UTC).isoformat(timespec="seconds")
                if module_key:
                    try:
                        from biointel.nextgen.intelligence import persist_run_snapshot
                        run_id = persist_run_snapshot(
                            project_root=PROJECT_ROOT,
                            module_key=module_key,
                            signature=signature,
                            parameters=parameters,
                            summary=summary,
                            result=result,
                            extras=extras,
                            completed_at_utc=completed_at,
                        )
                        summary["run_id"] = run_id
                    except Exception as persist_exc:
                        summary["run_registry_warning"] = f"{type(persist_exc).__name__}: {persist_exc}"[:500]
                state = RunState(
                    signature=signature,
                    result=result,
                    summary=summary,
                    secondary=secondary,
                    extras=extras,
                    parameters=dict(parameters),
                    completed_at_utc=completed_at,
                )
                st.session_state[state_key] = state
                status.update(label="Analysis completed", state="complete", expanded=False)
            st.toast("Analysis completed and cached for this module.", icon="✅")
            current = state
        except MemoryError as exc:
            error_id = _safe_error_id(state_key, exc)
            st.error(f"Analysis stopped before exhausting system memory · {error_id}")
            st.info("Reduce the interactive dataset or use the staged background-job workflow.")
            return None
        except Exception as exc:
            error_id = _safe_error_id(state_key, exc)
            st.error(f"Analysis failed safely · {error_id}")
            with st.expander("Technical recovery details", expanded=False):
                st.code(f"{type(exc).__name__}: {exc}")
                st.caption("The error identifier is deterministic for this module and failure signature.")
            return None
    current = st.session_state.get(state_key)
    if isinstance(current, RunState):
        if current.signature == signature:
            st.success(f"Cached run ready · completed {current.completed_at_utc}")
            return current
        st.warning("Cached results are outdated. Run the analysis to refresh them.")
    return None


def render_results_workbench(
    *,
    run_state: RunState | None,
    key: str,
    chart_renderer: Callable[[pd.DataFrame, pd.DataFrame | None, dict[str, pd.DataFrame]], None],
    boundary: str,
    module_key: str | None = None,
) -> None:
    if run_state is None:
        st.info("No current analysis result. Configure the workspace and select **Run analysis**.")
        return
    result = run_state.result
    secondary = run_state.secondary
    extras = run_state.extras
    if module_key:
        try:
            from biointel.ui.nextgen_intelligence import apply_linked_context, render_linked_context_banner
            result, secondary, extras, linked_context = apply_linked_context(module_key, result, secondary, extras)
            if linked_context:
                render_linked_context_banner(module_key, key=f"{key}_results_linked")
        except Exception:
            linked_context = None
    summary = run_state.summary
    left, right = st.columns([2.2, 1], gap="large")
    with left:
        chart_renderer(result, secondary, extras)
    with right:
        st.markdown("#### Run overview")
        scalar = {k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool)) or v is None}
        if scalar:
            smart_dataframe(
                pd.DataFrame([{"Metric": str(k).replace("_", " ").title(), "Value": v} for k, v in scalar.items()]),
                height=min(360, 90 + 32 * len(scalar)),
                key=f"{key}_summary_table",
            )
        else:
            st.caption("Structured summary is available in the evidence manifest.")

    if module_key:
        try:
            from biointel.peak_potential.catalog import domain_for
            from biointel.peak_potential.quality import audit_frame
            from biointel.peak_potential.workflow import interpretation_summary, requirements_for
            from biointel.ui.navigation import PAGE_BY_KEY

            page = PAGE_BY_KEY.get(module_key)
            page_title = page.title if page is not None else module_key.replace("_", " ").title()
            category = page.category if page is not None else "Scientific Module"
            domain = domain_for(page_key=module_key, category=category, title=page_title)
            requirements = requirements_for(module_key, domain)
            result_audit = audit_frame(result).to_dict()
            interpretation = interpretation_summary(
                title=page_title,
                domain=domain,
                run_manifest={"status": "completed", **summary},
                frame_audits={"results": result_audit},
                visual_audits={},
                requirements=requirements,
            )
            st.markdown("#### Interpretation and next action")
            st.markdown(f"**Main finding:** {interpretation['finding']}")
            st.caption(f"Confidence: {interpretation['confidence']}")
            i1, i2 = st.columns(2, gap="large")
            with i1:
                st.markdown("**Limitations / confounders**")
                for item in interpretation["limitations"][:6]:
                    st.markdown(f"- {item}")
            with i2:
                st.markdown("**Recommended next actions**")
                for item in interpretation["recommended_next_actions"][:6]:
                    st.markdown(f"- {item}")
        except Exception:
            pass
    st.markdown("#### Result records")
    scientific_table(
        result.head(max(1, int(run_state.parameters.get("top_n", 40)))),
        key=f"{key}_results",
        selectable=True,
        height=440,
        file_name=f"{key}_filtered_results.csv",
    )
    if secondary is not None and not secondary.empty:
        with st.expander("Grouped or secondary analysis", expanded=False):
            scientific_table(
                secondary,
                key=f"{key}_secondary",
                height=330,
                file_name=f"{key}_secondary.csv",
            )
    if extras:
        with st.expander(f"Advanced result tables · {len(extras)}", expanded=False):
            names = [name for name, table in extras.items() if table is not None and not table.empty]
            if names:
                selected = st.selectbox("Result table", names, format_func=lambda value: value.replace("_", " ").title(), key=f"{key}_extra_choice")
                scientific_table(
                    extras[selected],
                    key=f"{key}_extra_{selected}",
                    height=360,
                    file_name=f"{key}_{selected}.csv",
                )
            else:
                st.caption("No additional tables were produced.")
    with st.expander("Interpretation boundary", expanded=False):
        st.warning(boundary, icon="⚠️")


def build_export_bundle(
    *,
    module_key: str,
    run_state: RunState,
    manifest: dict[str, Any],
    max_rows_per_table: int = 100_000,
) -> bytes:
    buffer = io.BytesIO()
    index: dict[str, Any] = {"module_key": module_key, "tables": {}}

    def write_table(archive: zipfile.ZipFile, name: str, table: pd.DataFrame) -> None:
        safe_name = _safe_name(name)
        limited = table.head(max(1, int(max_rows_per_table)))
        payload = limited.to_csv(index=False).encode("utf-8")
        archive.writestr(safe_name, payload)
        index["tables"][safe_name] = {
            "source_rows": int(len(table)),
            "exported_rows": int(len(limited)),
            "columns": int(len(table.columns)),
            "truncated": bool(len(limited) < len(table)),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        write_table(archive, "results.csv", run_state.result)
        if run_state.secondary is not None and not run_state.secondary.empty:
            write_table(archive, "secondary_summary.csv", run_state.secondary)
        for name, table in run_state.extras.items():
            if table is not None and not table.empty:
                write_table(archive, f"tables/{_safe_name(name)}.csv", table)
        archive.writestr("evidence_manifest.json", json.dumps(manifest, indent=2, sort_keys=True, default=str))
        archive.writestr("bundle_index.json", json.dumps(index, indent=2, sort_keys=True, default=str))
        archive.writestr(
            "README.txt",
            "BioIntel AI scientific result bundle\n"
            f"Module: {module_key}\n"
            f"Completed: {run_state.completed_at_utc}\n\n"
            "Tables are bounded to protect memory; bundle_index.json records any truncation.\n"
            "This package contains exploratory outputs and an explicit scientific boundary.\n",
        )
    return buffer.getvalue()


def render_export_panel(
    *,
    module_key: str,
    run_state: RunState | None,
    manifest: dict[str, Any] | None,
    key: str,
) -> None:
    if run_state is None or manifest is None:
        st.info("Run the analysis before creating an export package.")
        return
    bundle_state_key = f"{key}_prepared_bundle"
    bundle_hash_key = f"{key}_prepared_bundle_hash"
    bundle_revision = f"{run_state.signature}:{manifest.get('manifest_sha256', '')}"
    if st.session_state.get(bundle_hash_key) != bundle_revision:
        st.session_state.pop(bundle_state_key, None)
    c1, c2, c3 = st.columns(3)
    if c1.button(
        "Prepare complete ZIP",
        width="stretch",
        key=f"{key}_prepare_bundle",
        help="Generated on demand so parameter changes and reruns remain responsive.",
    ):
        try:
            st.session_state[bundle_state_key] = build_export_bundle(
                module_key=module_key, run_state=run_state, manifest=manifest
            )
            st.session_state[bundle_hash_key] = bundle_revision
        except Exception as exc:
            st.error(f"Export preparation failed safely · {_safe_error_id(key, exc)}")
    if st.session_state.get(bundle_state_key):
        c1.download_button(
            "Download complete ZIP",
            st.session_state[bundle_state_key],
            f"{module_key}_complete_result_bundle.zip",
            "application/zip",
            width="stretch",
            key=f"{key}_bundle",
        )
    c2.download_button(
        "Results CSV",
        run_state.result.head(100_000).to_csv(index=False).encode("utf-8"),
        f"{module_key}_results.csv",
        "text/csv",
        width="stretch",
        key=f"{key}_results_csv",
    )
    c3.download_button(
        "Evidence manifest",
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        f"{module_key}_evidence_manifest.json",
        "application/json",
        width="stretch",
        key=f"{key}_manifest_json",
    )
    with st.expander("Advanced individual downloads", expanded=False):
        if run_state.secondary is not None and not run_state.secondary.empty:
            st.download_button(
                "Grouped summary CSV",
                run_state.secondary.head(100_000).to_csv(index=False).encode("utf-8"),
                f"{module_key}_grouped_summary.csv",
                "text/csv",
                key=f"{key}_secondary_csv",
            )
        for name, table in run_state.extras.items():
            if table is not None and not table.empty:
                st.download_button(
                    f"{name.replace('_', ' ').title()} CSV",
                    table.head(100_000).to_csv(index=False).encode("utf-8"),
                    f"{module_key}_{name}.csv",
                    "text/csv",
                    key=f"{key}_{name}_csv",
                )
    smart_json(manifest, title="Run evidence manifest", download_name=f"{module_key}_evidence_manifest.json", key=f"{key}_manifest_view")
