from __future__ import annotations

import sys
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.theme import apply_theme, hero
from biointel.utils.large_files import (
    load_registry,
    register_local_file,
    remove_registered_paths,
)
from biointel.utils.local_data import (
    delete_managed_files,
    directory_size_bytes,
    list_managed_files,
)
from biointel.data.neuro_data_fabric import UniversalNeuroDataFabric, SUPPORTED_FORMATS

st.set_page_config(page_title="Local Data Manager · BioIntel AI", page_icon="🧹", layout="wide")
apply_theme()
hero(
    "🧹 Local Data Manager & Universal Neuro Data Fabric",
    "Validated ingestion, format conversion, PHI scanning, and BIDS/NWB validation across 18 neuro & biological formats.",
    eyebrow="BioIntel AI · Local-first storage & Universal Fabric",
)
st.caption("No account or login is used. Paths and generated files stay on this computer.")

fabric_tab, large_tab, managed_tab = st.tabs(["🚀 P0 Universal Neuro Data Fabric", "Large-file intake", "Generated files"])

fabric = UniversalNeuroDataFabric(str(ROOT / "UserData" / "data_fabric"))

with fabric_tab:
    st.subheader("Universal Neuro & Omics Data Ingestion Fabric")
    st.write("Supports 18 validated formats: DICOM, NIfTI, BIDS, EEG/MEG-BIDS, EDF, BDF, FIF, BrainVision, NWB, OME-Zarr, AnnData H5AD, MuData H5MU, FASTQ, BAM, CRAM, VCF, CSV, Parquet.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🔍 Format Detection & Metadata Extraction")
        input_path = st.text_input("Enter local file/folder path for inspection", placeholder=r"C:\Data\brain_scan.nii.gz")
        if st.button("Inspect & Extract Metadata", key="btn_inspect"):
            if input_path.strip() and Path(input_path.strip()).exists():
                fmt = fabric.detect_format(input_path.strip())
                st.success(f"Detected Format: **{fmt}**")
                meta = fabric.extract_metadata(input_path.strip())
                st.json(asdict(meta))
            else:
                st.error("Please enter a valid existing file or directory path.")

        st.divider()
        st.markdown("#### 🛡️ PHI Risk Scanner & De-Identification")
        phi_file = st.text_input("File path to scan for PHI tags", placeholder=r"C:\Clinical\patient_record.csv")
        if st.button("Scan & De-Identify", key="btn_phi"):
            if phi_file.strip() and Path(phi_file.strip()).exists():
                phi_rep = fabric.scan_phi_deidentify(phi_file.strip())
                if phi_rep.phi_detected:
                    st.warning(f"PHI Risk Score: {phi_rep.risk_score}. Detected Tags: {phi_rep.detected_tags}")
                    if phi_rep.deidentified_output_path:
                        st.info(f"De-identified copy created at: `{phi_rep.deidentified_output_path}`")
                else:
                    st.success("No PHI risks detected in header/text content.")
            else:
                st.error("Please enter a valid file path.")

    with col2:
        st.markdown("#### 📐 BIDS & NWB Dataset Validator")
        val_path = st.text_input("BIDS or NWB dataset root path", placeholder=r"C:\Datasets\bids_study")
        val_type = st.selectbox("Validation Standard", ["BIDS", "NWB"])
        if st.button("Run Standard Validation", key="btn_validate"):
            if val_path.strip():
                val_rep = fabric.validate_bids_or_nwb(val_path.strip(), val_type)
                if val_rep.is_valid:
                    st.success(f"{val_type} validation passed!")
                else:
                    st.error(f"{val_type} validation failed with errors:")
                    for err in val_rep.errors:
                        st.write(f"- ❌ {err}")
                if val_rep.warnings:
                    st.warning("Warnings:")
                    for w in val_rep.warnings:
                        st.write(f"- ⚠️ {w}")
            else:
                st.error("Please enter a dataset path.")

        st.divider()
        st.markdown("#### 🌐 OpenNeuro & DANDI Public Import Adapter")
        acc = st.text_input("Dataset Accession ID", placeholder="ds000248 or 000003")
        prov = st.selectbox("Public Repository", ["OpenNeuro", "DANDI"])
        if st.button("Import & Cache Offline Manifest", key="btn_import"):
            if acc.strip():
                res = fabric.import_from_openneuro_or_dandi(acc.strip(), prov)
                st.success(f"Dataset {acc.strip()} imported and cached successfully!")
                st.json(res)
            else:
                st.error("Please enter an accession ID.")

with large_tab:
    st.subheader("Register a large local scientific file")
    st.info(
        "For FASTQ, BAM, mzML, H5AD and other large inputs, enter the full local path. "
        "BioIntel stores only a reference and metadata; it does not copy the file or load it all into RAM."
    )
    source_path = st.text_input(
        "Full local file path",
        placeholder=r"C:\Research\cohort\sample_R1.fastq.gz",
        help="The path must be accessible from the computer running BioIntel AI.",
    )
    label = st.text_input("Optional label", placeholder="Cohort A · raw reads")
    compute_hash = st.checkbox(
        "Compute SHA-256 now",
        value=False,
        help="Recommended for evidence packages. Hashing multi-gigabyte files can take several minutes.",
    )
    if st.button("Register local file", type="primary", disabled=not source_path.strip()):
        try:
            reference = register_local_file(
                ROOT,
                source_path.strip(),
                label=label,
                compute_hash=compute_hash,
            )
        except (OSError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.success(
                f"Registered {reference.name} ({reference.size_bytes / 1024**3:.3f} GiB) "
                "without copying the source file."
            )
            st.rerun()

    registered = load_registry(ROOT)
    if registered:
        frame = pd.DataFrame(registered)
        frame["size_gib"] = frame["size_bytes"].astype(float) / 1024**3
        visible = frame[
            ["label", "name", "extension", "size_gib", "sha256", "source_path", "registered_at"]
        ].rename(
            columns={
                "label": "Label",
                "name": "File",
                "extension": "Type",
                "size_gib": "Size GiB",
                "sha256": "SHA-256",
                "source_path": "Local path",
                "registered_at": "Registered",
            }
        )
        st.dataframe(visible, width="stretch", hide_index=True)
        selected_paths = st.multiselect(
            "Remove registry entries",
            [str(row.get("source_path", "")) for row in registered],
        )
        if st.button("Remove selected references", disabled=not selected_paths):
            removed = remove_registered_paths(ROOT, selected_paths)
            st.success(f"Removed {removed} registry reference(s). Source files were not deleted.")
            st.rerun()
    else:
        st.caption("No large local files are registered yet.")

with managed_tab:
    st.subheader("Manage generated files")
    files = list_managed_files(ROOT)
    if files:
        df = pd.DataFrame(files)
        df["size_mb"] = df["size_bytes"].astype(float) / 1024**2
        st.dataframe(
            df[["relative_path", "size_mb", "modified_at"]].rename(
                columns={
                    "relative_path": "Path",
                    "size_mb": "Size (MB)",
                    "modified_at": "Modified",
                }
            ),
            width="stretch",
            hide_index=True,
        )
        if st.button("Delete all generated files", type="secondary"):
            deleted_count = delete_managed_files(ROOT)
            st.success(f"Deleted {deleted_count} file(s).")
            st.rerun()
    else:
        st.caption("No generated files present.")

# STEP187_PAGE_EXCELLENCE_HOOK
from biointel.page_excellence_v187.ui import (
    render_step187_page_excellence as _render_step187_page_excellence,
)

_render_step187_page_excellence(__file__)
