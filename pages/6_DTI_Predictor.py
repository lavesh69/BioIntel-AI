from __future__ import annotations

import html
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.chemistry.descriptors import calculate_descriptors
from biointel.chemistry.molecule_visualization import molecule_png
from biointel.dti.predictor import (
    batch_predict_dti,
    predict_dti_pair,
)
from biointel.quality.model_audit import audit_model_directory
from biointel.reports.pdf_report import build_structured_pdf
from biointel.training.model_artifact import load_model_artifact_cached
from biointel.training.model_catalog import (
    default_model_path,
    sync_model_catalog,
)
from biointel.ui.brand import (
    BRAND,
    branded_model_identity,
    branded_page_title,
)
from biointel.ui.components import smart_json
from biointel.ui.theme import (
    apply_theme,
    badge,
    hero,
    section_title,
)
from biointel.ui.scientific_visuals import build_dti_prediction_visuals, render_generic_visual_explorer, render_visual_collection
from biointel.ui.workflow import analysis_run, read_uploaded_table, render_upload_preflight
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(
    page_title=branded_page_title("DTI Prediction Studio"),
    page_icon="🔬",
    layout="wide",
)

apply_theme()
from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/6_DTI_Predictor.py", key_prefix="6_dti_predictor", expanded=False)

hero(
    "From molecule and protein to an interpretable prediction.",
    (
        "Use a registered local model with exact feature-schema checks, "
        "conformal uncertainty and applicability warnings."
    ),
    eyebrow=f"{BRAND.name} · DTI Prediction Studio",
    chips=["Registered models", "Quality gates", "Uncertainty", "Applicability"],
)

models_directory = ROOT / "models"
catalog = [entry for entry in sync_model_catalog(models_directory) if entry.state != "archived"]
model_quality = audit_model_directory(models_directory)
audit_by_model = {item["model_file"]: item for item in model_quality["models"]}
model_paths = [models_directory / entry.filename for entry in catalog]
preferred_model = default_model_path(models_directory, require_compatible=True)

if not model_paths:
    st.error("No trusted model is available. Train and save a model before predicting.")
    st.stop()


def _model_label(path: Path) -> str:
    sidecar = path.with_suffix(".json")
    payload: dict[str, object] = {}
    if sidecar.is_file():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    proxy = SimpleNamespace(
        model_name=str(payload.get("model_name") or path.stem),
        model_version=str(payload.get("model_version") or "local"),
        task_type=str(payload.get("task_type") or "model"),
        synthetic_demo=bool(payload.get("synthetic_demo", False)),
    )
    identity = branded_model_identity(path, proxy, audit_by_model.get(path.name, {}))
    return f"{identity.display_name} · {identity.quality_label}"


default_index = model_paths.index(preferred_model) if preferred_model in model_paths else 0
selected_model = st.selectbox(
    "Model",
    model_paths,
    index=default_index,
    format_func=_model_label,
    help="Branded names show the algorithm, version, evidence tier and audited quality score. The technical filename remains available in model metadata.",
)

try:
    artifact = load_model_artifact_cached(
        selected_model,
        trusted_root=models_directory,
    )
except Exception as exc:
    st.error(f"Model could not be loaded: {exc}")
    st.stop()

molecule_library_path = ROOT / "data" / "libraries" / "molecule_library_240.csv"
protein_library_path = ROOT / "data" / "libraries" / "protein_library_24.csv"
molecule_library = (
    read_csv_cached(molecule_library_path) if molecule_library_path.is_file() else pd.DataFrame()
)
protein_library = (
    read_csv_cached(protein_library_path) if protein_library_path.is_file() else pd.DataFrame()
)

metadata = artifact.metadata
selected_quality = audit_by_model.get(selected_model.name, {})
model_brand = branded_model_identity(selected_model, metadata, selected_quality)
badge(
    f"● Tier {model_brand.tier_code} · {model_brand.tier_label}",
    model_brand.status_tone,
)
section_title("Selected model", "◈")
st.markdown(
    f"""
    <div class="bio-model-identity" aria-label="Selected model identity">
      <div class="bio-model-card bio-model-card--primary">
        <span class="bio-model-card-label">BioIntel model</span>
        <span class="bio-model-card-value">{html.escape(model_brand.display_name)}</span>
        <span class="bio-model-card-detail">Artifact: {html.escape(selected_model.name)}</span>
      </div>
      <div class="bio-model-card"><span class="bio-model-card-label">Task</span><span class="bio-model-card-value">{html.escape(metadata.task_type.title())}</span><span class="bio-model-card-detail">Registered feature schema</span></div>
      <div class="bio-model-card"><span class="bio-model-card-label">Validation split</span><span class="bio-model-card-value">{html.escape(metadata.split_strategy.replace("_", " ").title())}</span><span class="bio-model-card-detail">Leakage gate: {"Passed" if selected_quality.get("robust_split_passed") else "Not passed"}</span></div>
      <div class="bio-model-card"><span class="bio-model-card-label">Evidence tier</span><span class="bio-model-card-value">Tier {html.escape(model_brand.tier_code)}</span><span class="bio-model-card-detail">{html.escape(model_brand.tier_label)}</span></div>
      <div class="bio-model-card"><span class="bio-model-card-label">Quality gate</span><span class="bio-model-card-value">{float(selected_quality.get("score", 0.0)):.0f}/100</span><span class="bio-model-card-detail">{"Release eligible" if selected_quality.get("release_eligible") else "Exploratory only"}</span></div>
    </div>
    <div class="bio-evidence-tier">
      <div class="bio-evidence-tier-mark">{html.escape(model_brand.tier_code)}</div>
      <div><strong>{html.escape(model_brand.evidence_label)}</strong><span>Permitted use: {"scientific release under the approved model policy" if selected_quality.get("release_eligible") else "software demonstration and exploratory research only"}. Clinical, safety or therapeutic decisions are not authorized.</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)
if not selected_quality.get("release_eligible", False):
    with st.expander("Why scientific release is blocked", expanded=False):
        for blocker in selected_quality.get("blockers", []):
            st.markdown(f"- {blocker}")
    exploratory_acknowledgement = st.checkbox(
        "I understand this model is exploratory/demo-only and its output cannot be used as scientific hit-selection evidence.",
        value=False,
        key="dti_exploratory_acknowledgement",
        help="This acknowledgement enables the demonstration prediction button; it does not change the model evidence tier.",
    )
else:
    exploratory_acknowledgement = True

with st.expander("Model metadata and held-out metrics"):
    smart_json(
        {
            "trained_at_utc": metadata.trained_at_utc,
            "dataset_name": metadata.dataset_name,
            "dataset_version": metadata.dataset_version,
            "train_rows": metadata.train_rows,
            "validation_rows": metadata.validation_rows,
            "test_rows": metadata.test_rows,
            "threshold_strategy": metadata.threshold_strategy,
            "decision_threshold": metadata.decision_threshold,
            "calibration_method": metadata.calibration_method,
            "validation_metrics": metadata.validation_metrics,
            "final_test_metrics": metadata.metrics,
            "data_quality_summary": metadata.data_quality_summary,
            "uncertainty_calibration": metadata.uncertainty_calibration,
        }
    )

section_title("Prediction workspace", "🔬")
single_tab, batch_tab = st.tabs(["Single prediction", "Batch prediction"])

with single_tab:
    input_mode = st.radio(
        "Input mode",
        ["Bundled library example", "Custom pair"],
        horizontal=True,
    )

    if (
        input_mode == "Bundled library example"
        and not molecule_library.empty
        and not protein_library.empty
    ):
        selector_left, selector_right = st.columns(2)
        selected_drug_id = selector_left.selectbox(
            "Molecule",
            molecule_library["drug_id"].tolist(),
            format_func=lambda value: (
                f"{value} · "
                + str(
                    molecule_library.loc[
                        molecule_library["drug_id"] == value,
                        "canonical_smiles",
                    ].iloc[0]
                )[:48]
            ),
        )
        selected_target_id = selector_right.selectbox(
            "Protein target",
            protein_library["target_id"].tolist(),
            format_func=lambda value: (
                f"{value} · "
                + str(
                    protein_library.loc[
                        protein_library["target_id"] == value,
                        "target_family",
                    ].iloc[0]
                )
            ),
        )
        drug_row = molecule_library.loc[molecule_library["drug_id"] == selected_drug_id].iloc[0]
        target_row = protein_library.loc[protein_library["target_id"] == selected_target_id].iloc[0]
        smiles = str(drug_row["canonical_smiles"])
        protein_sequence = str(target_row["protein_sequence"])
        st.code(smiles, language=None)
        st.text_area(
            "Selected protein sequence",
            value=protein_sequence,
            height=140,
            disabled=True,
        )
    else:
        left, right = st.columns(2)
        smiles = left.text_input(
            "Drug SMILES",
            value=str(st.session_state.get("dti_smiles", "CC(=O)OC1=CC=CC=C1C(=O)O")),
            key="dti_predict_smiles",
        )
        protein_sequence = right.text_area(
            "Target protein sequence",
            value=("MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE"),
            height=140,
        )

    st.markdown(
        f"""<div class="bio-action-readiness" aria-label="Prediction readiness">
        <span class="bio-ready">✓ <b>Molecule</b> selected</span>
        <span class="bio-ready">✓ <b>Protein</b> selected</span>
        <span class="{"bio-ready" if exploratory_acknowledgement else "bio-blocked"}">{"✓" if exploratory_acknowledgement else "!"} <b>Demo acknowledgement</b> {"complete" if exploratory_acknowledgement else "required"}</span>
        </div>""",
        unsafe_allow_html=True,
    )
    if not exploratory_acknowledgement:
        st.caption(
            "Tick the exploratory-use acknowledgement above to enable this demonstration prediction."
        )
    predict_clicked = st.button(
        "Predict interaction",
        type="primary",
        disabled=not exploratory_acknowledgement,
        help=(
            "Run the registered model for an exploratory prediction."
            if exploratory_acknowledgement
            else "Enable by accepting the exploratory-use acknowledgement above."
        ),
    )

    if predict_clicked:
        try:
            prediction = predict_dti_pair(
                artifact,
                smiles,
                protein_sequence,
            )
        except Exception as exc:
            st.error(f"Prediction failed: {exc}")
        else:
            if prediction.task_type == "classification":
                result_columns = st.columns(4)
                result_columns[0].metric(
                    "Predicted class",
                    prediction.predicted_class,
                )
                result_columns[1].metric(
                    "Positive probability",
                    f"{prediction.positive_probability:.3f}",
                )
                result_columns[2].metric(
                    "Decision threshold",
                    f"{prediction.decision_threshold:.3f}",
                )
                similarity_value = (
                    f"{prediction.nearest_training_drug_similarity:.2f}"
                    if prediction.nearest_training_drug_similarity is not None
                    else "Unavailable"
                )
                result_columns[3].metric(
                    "Nearest training-drug similarity",
                    similarity_value,
                )
            else:
                result_columns = st.columns(3)
                result_columns[0].metric(
                    "Predicted pActivity",
                    f"{prediction.predicted_p_activity:.3f}",
                )
                result_columns[1].metric(
                    "Protein length",
                    prediction.protein_length,
                )
                similarity_value = (
                    f"{prediction.nearest_training_drug_similarity:.2f}"
                    if prediction.nearest_training_drug_similarity is not None
                    else "Unavailable"
                )
                result_columns[2].metric(
                    "Nearest training-drug similarity",
                    similarity_value,
                )

            st.info(prediction.confidence)
            if prediction.prediction_set is not None:
                st.success(
                    "Conformal prediction set: {"
                    + ", ".join(map(str, prediction.prediction_set))
                    + "}"
                )
            if prediction.prediction_interval_lower is not None:
                st.success(
                    f"Conformal pActivity interval: [{prediction.prediction_interval_lower:.3f}, "
                    f"{prediction.prediction_interval_upper:.3f}]"
                )
            if prediction.applicability_status == "Within basic training range":
                st.success(prediction.applicability_status)
            else:
                st.warning(prediction.applicability_status)
            st.caption(prediction.applicability_details)

            structure_left, descriptor_right = st.columns([1, 2])
            descriptor_result = {}
            try:
                structure_left.image(
                    molecule_png(prediction.canonical_smiles),
                    caption=prediction.canonical_smiles,
                )
            except Exception as exc:
                structure_left.warning(f"Structure rendering unavailable: {exc}")
            try:
                descriptor_result = calculate_descriptors(prediction.canonical_smiles)
            except (TypeError, ValueError, RuntimeError) as exc:
                descriptor_right.warning(f"Descriptor panel unavailable: {exc}")
            else:
                descriptor_right.dataframe(
                    pd.DataFrame(
                        [
                            {"Descriptor": key, "Value": value}
                            for key, value in descriptor_result.items()
                            if key not in {"lipinski_rules"}
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

            payload = asdict(prediction)
            render_visual_collection(
                build_dti_prediction_visuals(payload, descriptor_result),
                key="dti_single_prediction_visuals",
                heading="Prediction visual analytics",
            )
            st.download_button(
                "Download prediction JSON",
                json.dumps(payload, indent=2, default=str),
                "dti_prediction.json",
                "application/json",
            )
            st.download_button(
                "Download prediction PDF",
                build_structured_pdf(
                    f"{BRAND.name} — DTI Prediction",
                    {
                        "Prediction": payload,
                        "Model": {
                            "display_name": model_brand.display_name,
                            "model_name": metadata.model_name,
                            "model_version": metadata.model_version,
                            "dataset_name": metadata.dataset_name,
                            "split_strategy": metadata.split_strategy,
                            "final_test_metrics": metadata.metrics,
                        },
                    },
                ),
                "dti_prediction.pdf",
                "application/pdf",
            )

            if prediction.synthetic_demo_model:
                st.error(
                    "This model was trained on synthetic demonstration data. "
                    "The output has no biological or clinical validity."
                )

with batch_tab:
    st.write(
        "Required columns: `canonical_smiles`, `protein_sequence`. Optional column: `sample_id`."
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
        key="predictor_batch_source",
    )
    batch_dataframe: pd.DataFrame | None = None

    if batch_source.startswith("Bundled"):
        if "5,000" in batch_source:
            sample_name = "batch_prediction_sample_5000.csv"
        elif "2,000" in batch_source:
            sample_name = "batch_prediction_sample_2000.csv"
        elif "1,000" in batch_source:
            sample_name = "batch_prediction_sample_1000.csv"
        else:
            sample_name = "batch_prediction_sample_250.csv"
        sample_path = ROOT / "data" / "packs" / sample_name
        if sample_path.is_file():
            batch_dataframe = read_csv_cached(sample_path)
            st.download_button(
                "Download bundled batch sample",
                sample_path.read_bytes(),
                sample_path.name,
                "text/csv",
            )
        else:
            st.error("Bundled batch sample is missing. Run BUILD_DATA_AND_MODELS_WINDOWS.bat.")
    else:
        batch_upload = st.file_uploader(
            "Upload batch CSV",
            type=["csv"],
            key="batch_csv",
        )
        render_upload_preflight(
            batch_upload,
            key="dti_batch_prediction",
            allowed_extensions=["csv"],
            soft_limit_mb=10,
            hard_limit_mb=25,
        )
        if batch_upload is not None:
            if batch_upload.size > 25 * 1024 * 1024:
                st.error("Batch CSV exceeds the 25 MB limit.")
            else:
                try:
                    batch_dataframe = read_uploaded_table(batch_upload)
                except Exception as exc:
                    st.error(f"Could not read batch CSV: {exc}")

    if batch_dataframe is not None:
        st.dataframe(
            batch_dataframe.head(50),
            width="stretch",
            hide_index=True,
        )
        if st.button(
            "Run batch prediction",
            disabled=not exploratory_acknowledgement,
            help="Release-blocked models require explicit exploratory-use acknowledgement.",
        ):
            try:
                with analysis_run(
                    f"Building features and predicting {len(batch_dataframe):,} molecule–protein pairs",
                    expanded=True,
                ) as batch_run:
                    batch_run.stage("Validating batch schema", progress=0.10)
                    batch_output = batch_predict_dti(
                        artifact,
                        batch_dataframe,
                        max_rows=min(max(len(batch_dataframe), 1), 5000),
                        n_jobs=-1,
                    )
                    batch_run.stage("Formatting prediction and error records", progress=0.95)
            except Exception as exc:
                st.error(f"Batch prediction failed: {exc}")
            else:
                error_count = int(batch_output["error"].astype(bool).sum())
                st.success(
                    f"Processed {len(batch_output)} rows; {error_count} rows returned errors."
                )
                st.dataframe(
                    batch_output,
                    width="stretch",
                    hide_index=True,
                )
                render_generic_visual_explorer(
                    batch_output,
                    key="dti_batch_prediction_visuals",
                    heading="Batch prediction visual analytics",
                )
                st.download_button(
                    "Download batch results CSV",
                    batch_output.to_csv(index=False),
                    "dti_batch_predictions.csv",
                    "text/csv",
                )

st.info(
    "This is a computational prediction only. It does not establish physical "
    "binding, biological activity, safety, clinical effectiveness or approval. "
    "Experimental validation is required."
)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='dti_predictor', title='DTI Predictor', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='dti_predictor', title='DTI Predictor', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
