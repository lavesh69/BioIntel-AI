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

from biointel.dti.dataset_validation import validate_dti_dataset
from biointel.dti.feature_combiner import combine_dti_features
from biointel.sequence.parser import parse_sequence_text
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import apply_theme, hero
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.utils.exceptions import BioIntelError

st.set_page_config(page_title="DTI Feature Builder · BioIntel AI", page_icon="🧪", layout="wide")

apply_theme()

molecule_library_path = ROOT / "data" / "libraries" / "molecule_library_240.csv"
protein_library_path = ROOT / "data" / "libraries" / "protein_library_24.csv"
molecule_library = (
    read_csv_cached(molecule_library_path) if molecule_library_path.is_file() else pd.DataFrame()
)
protein_library = (
    read_csv_cached(protein_library_path) if protein_library_path.is_file() else pd.DataFrame()
)

hero(
    "🧪 Drug–Target Feature Builder",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption(
    "Create model-ready numeric features. Feature preparation does not make interaction predictions."
)

single_tab, batch_tab = st.tabs(["Single pair", "Dataset validator"])

with single_tab:
    input_mode = st.radio(
        "Input mode",
        ["Bundled library pair", "Custom pair"],
        horizontal=True,
        key="feature_pair_mode",
    )
    if (
        input_mode == "Bundled library pair"
        and not molecule_library.empty
        and not protein_library.empty
    ):
        left, right = st.columns(2)
        drug_id = left.selectbox(
            "Molecule",
            molecule_library["drug_id"].tolist(),
            key="feature_library_drug",
        )
        target_id = right.selectbox(
            "Protein target",
            protein_library["target_id"].tolist(),
            key="feature_library_target",
        )
        drug_row = molecule_library.loc[molecule_library["drug_id"] == drug_id].iloc[0]
        target_row = protein_library.loc[protein_library["target_id"] == target_id].iloc[0]
        smiles = str(drug_row["canonical_smiles"])
        protein_input = (
            f">{target_id}|{target_row['target_family']}\n{target_row['protein_sequence']}"
        )
        st.code(smiles, language=None)
        st.text_area(
            "Selected target sequence",
            value=protein_input,
            height=140,
            disabled=True,
        )
    else:
        left, right = st.columns(2)
        with left:
            smiles = st.text_input(
                "Drug SMILES",
                value="CC(=O)OC1=CC=CC=C1C(=O)O",
                key="dti_smiles",
            )
        with right:
            protein_input = st.text_area(
                "Target protein sequence or FASTA",
                value=(">example_target\nMKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE"),
                height=140,
            )

    with st.expander("Feature settings"):
        radius = st.number_input("Morgan radius", 0, 5, 2, key="dti_radius")
        n_bits = st.selectbox("Morgan bits", [256, 512, 1024, 2048, 4096], index=3, key="dti_bits")
        chirality = st.checkbox("Use chirality", value=True, key="dti_chirality")
        dipeptides = st.checkbox(
            "Include 400 dipeptide-composition features",
            value=False,
            help="Adds dimensionality and is intended for later model-training experiments.",
        )

    if st.button("Build DTI feature vector", type="primary"):
        try:
            parsed = parse_sequence_text(protein_input)
            combined = combine_dti_features(
                smiles=smiles,
                protein_sequence=parsed.sequence,
                radius=int(radius),
                n_bits=int(n_bits),
                use_chirality=chirality,
                include_dipeptides=dipeptides,
            )
            st.session_state["combined_features"] = combined
        except (BioIntelError, ValueError) as exc:
            st.error(str(exc))

    combined = st.session_state.get("combined_features")
    if combined is not None:
        cols = st.columns(4)
        cols[0].metric("Total features", combined.schema.feature_count)
        cols[1].metric("Drug features", combined.schema.drug_feature_count)
        cols[2].metric("Protein features", combined.schema.protein_feature_count)
        cols[3].metric("Protein length", combined.protein.sequence_length)
        st.success(
            "Feature vector generated successfully. No biological interaction claim was made."
        )
        st.code(combined.drug.canonical_smiles, language=None)

        preview = pd.DataFrame(
            {
                "Feature": combined.names[:80],
                "Value": combined.values[:80],
            }
        )
        st.subheader("Feature preview (first 80)")
        st.dataframe(preview, width="stretch", hide_index=True)
        render_generic_visual_explorer(
            preview,
            key="dti_feature_vector_visuals",
            heading="Feature-vector visual analytics",
        )

        feature_csv = combined.to_dataframe().to_csv(index=False)
        st.download_button(
            "Download feature vector CSV",
            feature_csv,
            "dti_feature_vector.csv",
            "text/csv",
        )
        st.download_button(
            "Download feature schema JSON",
            combined.schema_json(),
            "dti_feature_schema.json",
            "application/json",
        )
        summary = {
            "canonical_smiles": combined.drug.canonical_smiles,
            "protein_length": combined.protein.sequence_length,
            "schema": json.loads(combined.schema_json()),
        }
        st.download_button(
            "Download pair summary JSON",
            json.dumps(summary, indent=2),
            "dti_pair_summary.json",
            "application/json",
        )

with batch_tab:
    st.write(
        "Use a bundled pack or upload a CSV with `canonical_smiles`, "
        "`protein_sequence`, and either `label` or `p_activity`."
    )
    task = st.radio(
        "Dataset task",
        ["classification", "regression"],
        horizontal=True,
    )
    dataset_source = st.selectbox(
        "Dataset source",
        [
            "Foundation pack — 1,920 rows",
            "Extended pack — 5,760 rows",
            "Ultra pack — 16,000 rows",
            "Double Ultra pack — 32,000 rows",
            "5X Ultra pack — 160,000 rows",
            "Upload CSV",
        ],
        key="feature_dataset_source",
    )
    dataframe: pd.DataFrame | None = None
    if dataset_source == "Upload CSV":
        uploaded = st.file_uploader(
            "Upload DTI dataset CSV",
            type=["csv"],
        )
        render_upload_preflight(
            uploaded,
            key="dti_feature_builder",
            allowed_extensions=["csv"],
            soft_limit_mb=50,
            hard_limit_mb=250,
        )
        if uploaded is not None:
            try:
                dataframe = read_uploaded_table(uploaded)
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")
    else:
        if dataset_source.startswith("Foundation"):
            filename = "synthetic_foundation_dti_v2.csv"
        elif dataset_source.startswith("5X"):
            filename = "synthetic_5x_ultra_dti_v5.csv"
        elif dataset_source.startswith("Double"):
            filename = "synthetic_double_ultra_dti_v4.csv"
        elif dataset_source.startswith("Ultra"):
            filename = "synthetic_ultra_dti_v3.csv"
        else:
            filename = "synthetic_extended_dti_v2.csv"
        pack_path = ROOT / "data" / "packs" / filename
        if pack_path.is_file():
            dataframe = read_csv_cached(pack_path)
        else:
            st.error("Bundled pack is missing. Run BUILD_DATA_AND_MODELS_WINDOWS.bat.")

    if dataframe is not None:
        try:
            st.dataframe(
                dataframe.head(20),
                width="stretch",
            )
            report = validate_dti_dataset(
                dataframe,
                task,
            )
            metrics = st.columns(3)
            metrics[0].metric("Rows", report.total_rows)
            metrics[1].metric("Valid", report.valid_rows)
            metrics[2].metric("Invalid", report.invalid_rows)
            render_generic_visual_explorer(
                report.cleaned,
                key="dti_dataset_visuals",
                heading="Dataset feature and label analytics",
            )
            if not report.errors.empty:
                st.warning("Some rows were rejected. Review the row-specific errors below.")
                st.dataframe(report.errors, width="stretch", hide_index=True)
            st.download_button(
                "Download cleaned valid rows",
                report.cleaned.to_csv(index=False),
                "cleaned_dti_dataset.csv",
                "text/csv",
            )
            if not report.errors.empty:
                st.download_button(
                    "Download validation errors",
                    report.errors.to_csv(index=False),
                    "dti_validation_errors.csv",
                    "text/csv",
                )
        except Exception as exc:
            st.error(f"Dataset validation failed: {exc}")

st.divider()
st.info(
    "No DTI probability or binding claim is generated during feature preparation. A separately trained, "
    "evaluated and schema-compatible model is required in a later milestone."
)
st.caption("For educational and research use only. Not for clinical or therapeutic decisions.")

# STEP127_SCIENTIFIC_DEPTH_DTI_FEATURES
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('dti_features', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='dti_features', title='DTI Feature Builder', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='dti_features', title='DTI Feature Builder', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
