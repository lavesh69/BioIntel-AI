from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.streaming import stream_dataset_shape
from biointel.dti.batch_pipeline import run_streaming_batch_prediction
from biointel.dti.checkpoints import BatchCheckpointStore
from biointel.quality.model_audit import audit_model_directory
from biointel.training.model_artifact import load_model_artifact_cached
from biointel.training.model_catalog import default_model_path, sync_model_catalog
from biointel.ui.brand import branded_model_label_from_sidecar
from biointel.ui.components import smart_json
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import render_upload_preflight

MODELS = ROOT / "models"
REPORTS = ROOT / "reports" / "batch_jobs"
UPLOADS = REPORTS / "uploads"
REPORTS.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_ROWS = 250_000

st.set_page_config(page_title="Batch Prediction Jobs · BioIntel AI", page_icon="⚙️", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("batch_jobs", key_prefix="step116_23_Batch_Prediction_Jobs_batch_jobs_1", expanded=False)
hero(
    "⚙️ Resumable Batch Prediction Jobs",
    "File-backed, bounded-memory prediction with transactional checkpoints and safe resume.",
    eyebrow="BioIntel AI · Large-file Safe Workspace",
)
st.caption(
    "Inputs are preflight-scanned before inference. Complete outputs remain in SQLite so the UI never needs to load every result row."
)


def persist_upload(uploaded) -> Path:
    uploaded.seek(0)
    digest = hashlib.sha256()
    temporary = UPLOADS / (Path(uploaded.name).stem + ".uploading")
    written = 0
    try:
        with temporary.open("wb") as handle:
            while True:
                chunk = uploaded.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise ValueError("CSV exceeds the 1 GB per-file safety limit.")
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    target = UPLOADS / f"{digest.hexdigest()}_{Path(uploaded.name).name}"
    if target.exists():
        temporary.unlink(missing_ok=True)
    else:
        temporary.replace(target)
    return target


@st.cache_data(show_spinner=False)
def input_snapshot(
    path_text: str, modification_ns: int, size_bytes: int
) -> tuple[dict, pd.DataFrame]:
    del modification_ns, size_bytes
    path = Path(path_text)
    shape = stream_dataset_shape(path, chunk_size=10_000, max_rows=MAX_ROWS)
    preview = pd.read_csv(path, nrows=100, low_memory=False)
    return shape, preview


catalog = [entry for entry in sync_model_catalog(MODELS) if entry.state != "archived"]
quality_audit = audit_model_directory(MODELS)
audit_by_model = {item["model_file"]: item for item in quality_audit["models"]}
if not catalog:
    st.error("No candidate or active models are available.")
    st.stop()
default_path = default_model_path(MODELS, require_compatible=True)
model_names = [entry.filename for entry in catalog]
default_index = (
    model_names.index(default_path.name) if default_path and default_path.name in model_names else 0
)
selected_name = st.selectbox(
    "Model",
    model_names,
    index=default_index,
    format_func=lambda name: branded_model_label_from_sidecar(
        MODELS / name, audit_by_model.get(name, {})
    ),
)
artifact = load_model_artifact_cached(MODELS / selected_name, trusted_root=MODELS)
selected_quality = audit_by_model.get(selected_name, {})
if not selected_quality.get("release_eligible", False):
    st.info(
        f"{selected_name} is demonstration/candidate only (quality score {float(selected_quality.get('score', 0.0)):.1f}/100). "
        "Outputs must not be presented as independently validated scientific results."
    )

batch_source = st.radio(
    "Batch source",
    [
        "Bundled 250-row sample",
        "Bundled 1,000-row sample",
        "Bundled 2,000-row sample",
        "Bundled 5,000-row sample",
        "Upload CSV",
    ],
    horizontal=True,
)
source_path: Path | None = None
input_name = "bundled_batch_sample"
if batch_source.startswith("Bundled"):
    size = (
        "5000"
        if "5,000" in batch_source
        else "2000"
        if "2,000" in batch_source
        else "1000"
        if "1,000" in batch_source
        else "250"
    )
    source_path = ROOT / "data" / "packs" / f"batch_prediction_sample_{size}.csv"
    if not source_path.is_file():
        st.error("Bundled batch sample is missing.")
        st.stop()
    input_name = source_path.stem
    st.download_button(
        "Download bundled sample CSV", source_path.read_bytes(), source_path.name, "text/csv"
    )
else:
    uploaded = st.file_uploader("Batch CSV", type=["csv"])
    render_upload_preflight(
        uploaded,
        key="batch_prediction",
        allowed_extensions=["csv"],
        soft_limit_mb=100,
        hard_limit_mb=1024,
        block_large_files=False,
        module_key="batch_jobs",
    )
    if uploaded is None:
        st.info("Required columns: canonical_smiles and protein_sequence. sample_id is optional.")
        st.stop()
    if uploaded.size > MAX_UPLOAD_BYTES:
        st.error("CSV exceeds the 1 GB per-file safety limit.")
        st.stop()
    try:
        source_path = persist_upload(uploaded)
        input_name = Path(uploaded.name).stem
    except OSError as exc:
        st.error(f"Could not persist the upload safely: {exc}")
        st.stop()

assert source_path is not None
try:
    stat = source_path.stat()
    shape, preview = input_snapshot(str(source_path), stat.st_mtime_ns, stat.st_size)
except Exception as exc:
    st.error(f"Input preflight failed: {exc}")
    st.stop()
required = {"canonical_smiles", "protein_sequence"}
missing = required - set(shape["columns"])
if missing:
    st.error("Missing required columns: " + ", ".join(sorted(missing)))
    st.stop()
summary_columns = st.columns(3)
summary_columns[0].metric("Input rows", f"{int(shape['rows']):,}")
summary_columns[1].metric("Columns", len(shape["columns"]))
summary_columns[2].metric("Input size", f"{source_path.stat().st_size / (1024 * 1024):.1f} MB")
st.dataframe(preview, width="stretch", hide_index=True)

left, middle, right = st.columns(3)
chunk_size = left.select_slider("Chunk size", options=[100, 250, 500, 1000, 2000, 5000], value=1000)
workers = middle.select_slider("Feature workers", options=[1, 2, 4, 6, 8], value=4)
resume = right.checkbox("Resume existing checkpoint", value=True)
job_name = st.text_input("Job name", value=input_name)
safe_job_name = (
    "".join(
        character if character.isalnum() or character in "-_" else "_" for character in job_name
    ).strip("_")
    or "batch_job"
)
checkpoint = REPORTS / f"{safe_job_name}.sqlite3"
feature_cache = ROOT / "reports" / "feature_cache.sqlite3"
store = BatchCheckpointStore(checkpoint)
st.caption(f"Checkpoint: {checkpoint.relative_to(ROOT)}")
existing_count = store.count()
if existing_count:
    st.info(f"Existing transactional checkpoint contains {existing_count:,} result row(s).")

if st.button("Run or resume batch job", type="primary"):
    try:
        output, summary = run_streaming_batch_prediction(
            artifact,
            source_path,
            chunk_size=int(chunk_size),
            max_rows=MAX_ROWS,
            checkpoint_path=checkpoint,
            resume=resume,
            n_jobs=int(workers),
            feature_cache_path=feature_cache,
            preview_rows=100,
        )
    except Exception as exc:
        st.error(f"Batch job failed safely: {exc}")
    else:
        st.session_state["batch_job_output"] = output
        st.session_state["batch_job_summary"] = summary

output = st.session_state.get("batch_job_output")
summary = st.session_state.get("batch_job_summary")
if output is not None and summary is not None:
    columns = st.columns(6)
    columns[0].metric("Processed", f"{summary.processed_rows:,}")
    columns[1].metric("Success", f"{summary.success_rows:,}")
    columns[2].metric("Errors", f"{summary.error_rows:,}")
    columns[3].metric("Resumed", f"{summary.resumed_rows:,}")
    columns[4].metric("Rows/sec", summary.rows_per_second)
    columns[5].metric("Workers", summary.inference_workers)
    smart_json(asdict(summary))
    st.dataframe(output, width="stretch", hide_index=True)
    if summary.processed_rows <= 10_000:
        complete = BatchCheckpointStore(checkpoint).load()
        st.download_button(
            "Download complete batch output CSV",
            complete.to_csv(index=False),
            f"{safe_job_name}_predictions.csv",
            "text/csv",
        )
    elif checkpoint.stat().st_size <= 100 * 1024 * 1024:
        st.download_button(
            "Download transactional SQLite results",
            checkpoint.read_bytes(),
            checkpoint.name,
            "application/vnd.sqlite3",
        )
    else:
        st.info(f"Large result database retained locally at {checkpoint.relative_to(ROOT)}.")
    st.download_button(
        "Download job summary JSON",
        json.dumps(asdict(summary), indent=2, default=str),
        f"{safe_job_name}_summary.json",
        "application/json",
    )

st.info(
    "Checkpoints contain predictions and input identifiers. Manage or delete them from Local Data Manager when no longer needed."
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
