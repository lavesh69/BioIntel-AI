from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.public_branding import public_engine_name
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Engine Status · BioIntel AI",
    page_icon="⚙️",
    layout="wide",
)
apply_theme()

st.title("⚙️ BioIntel Scientific Engine Status")
st.caption(
    "Local runtime health, qualification state, component readiness and safe setup guidance under one BioIntel identity."
)


def _module_ready(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _binary_ready(*names: str) -> bool:
    return any(shutil.which(name) for name in names)


engines_data = [
    {
        "name": public_engine_name("Ollama"),
        "module": "Shiro AI Assistant",
        "status": "Ready" if _binary_ready("ollama") else "Setup available",
        "mode": "Local AI runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Local AI Runtime.",
    },
    {
        "name": public_engine_name("Tesseract OCR"),
        "module": "Shiro PDF & Image Intelligence",
        "status": "Ready" if _binary_ready("tesseract") else "Setup available",
        "mode": "Local document runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Document Recognition.",
    },
    {
        "name": public_engine_name("proteinmpnn"),
        "module": "AI Protein Design",
        "status": "Ready" if _binary_ready("proteinmpnn", "protein_mpnn_run.py") else "Qualification required",
        "mode": "BioIntel AI/GPU worker",
        "guide": "Open Engine Control Center and install the verified Protein Design pack.",
    },
    {
        "name": public_engine_name("rfdiffusion"),
        "module": "De Novo Backbone Design",
        "status": "Ready" if _binary_ready("rfdiffusion", "run_inference.py") else "Qualification required",
        "mode": "BioIntel AI/GPU worker",
        "guide": "Open Engine Control Center and install an approved Backbone Design pack.",
    },
    {
        "name": public_engine_name("openmm"),
        "module": "Molecular Dynamics",
        "status": "Ready" if _module_ready("openmm") else "Setup available",
        "mode": "BioIntel simulation runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Molecular Dynamics.",
    },
    {
        "name": "BioIntel Immunogenicity Prediction Engine",
        "module": "Vaccine & Neoantigen Design",
        "status": "Licence evidence required",
        "mode": "Controlled specialist runtime",
        "guide": "Record authorised component evidence in Legal & Component Notices before activation.",
    },
    {
        "name": public_engine_name("dorado"),
        "module": "Nanopore Epigenomics",
        "status": "Ready" if _binary_ready("dorado") else "Setup available",
        "mode": "BioIntel GPU sequencing runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Nanopore Processing.",
    },
    {
        "name": public_engine_name("minimap2"),
        "module": "Long-Read & Epigenomics",
        "status": "Ready" if _binary_ready("minimap2") else "Setup available",
        "mode": "BioIntel alignment runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Long-Read Alignment.",
    },
    {
        "name": public_engine_name("plink2"),
        "module": "GWAS & Proteogenomics",
        "status": "Ready" if _binary_ready("plink2") else "Setup available",
        "mode": "BioIntel population-genomics runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Population Genomics.",
    },
    {
        "name": public_engine_name("cellpose"),
        "module": "Spatial Omics & Microscopy",
        "status": "Ready" if _module_ready("cellpose") or _binary_ready("cellpose") else "Setup available",
        "mode": "BioIntel imaging AI runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Cell Segmentation.",
    },
    {
        "name": public_engine_name("scanpy"),
        "module": "Single-Cell Genomics",
        "status": "Ready" if _module_ready("scanpy") else "Setup available",
        "mode": "BioIntel single-cell runtime",
        "guide": "Run BIOINTEL_ENGINE_SETUP.bat and select Single-Cell Analysis.",
    },
]

ready_count = sum(item["status"] == "Ready" for item in engines_data)
setup_count = sum("Setup" in item["status"] for item in engines_data)
controlled_count = len(engines_data) - ready_count - setup_count

c1, c2, c3, c4 = st.columns(4)
c1.metric("Operational BioIntel engines", f"{ready_count} / {len(engines_data)}")
c2.metric("Guided setup available", setup_count)
c3.metric("Controlled activation", controlled_count)
c4.metric("Platform mode", "Local-first Windows")

st.markdown("---")
st.subheader("BioIntel engine readiness registry")
for engine in engines_data:
    icon = "✅" if engine["status"] == "Ready" else "🔒" if "required" in engine["status"].casefold() else "ℹ️"
    with st.expander(f"{icon} {engine['name']} — {engine['module']} ({engine['status']})"):
        left, right = st.columns(2)
        left.markdown(f"**Execution mode:** `{engine['mode']}`")
        left.markdown("**Component identity:** `BioIntel managed`")
        right.markdown(f"**Status:** `{engine['status']}`")
        right.markdown("**Legal notice:** `Available under Legal & Component Notices`")
        st.info(f"💡 **Setup guidance:** {engine['guide']}")

st.caption(
    "Internal executable identifiers are intentionally hidden from normal product surfaces. "
    "Required upstream identity and licence records remain available only in the legal notice workspace."
)
