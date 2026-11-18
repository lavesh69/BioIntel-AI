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

from biointel.sequence.dna_analysis import nucleotide_statistics
from biointel.sequence.parser import parse_sequence_text
from biointel.sequence.protein_analysis import protein_statistics
from biointel.sequence.validators import (
    SequenceType,
    detect_sequence_type,
    validate_for_type,
)
from biointel.ui.theme import (
    apply_theme,
    hero,
    section_title,
)
from biointel.ui.visual_polish import render_action_grid, render_metric_board

st.set_page_config(
    page_title="Quick Start · BioIntel AI",
    page_icon="🚀",
    layout="wide",
)

apply_theme()
hero(
    "Start with the right workflow in seconds.",
    (
        "Use guided actions for the most common sequence, molecule, "
        "training and prediction tasks. Advanced modules remain one "
        "click away in the sidebar."
    ),
    eyebrow="Quality-Hardened · Scientific Performance Quick Start",
    chips=["Internet", "PDB", "PubChem", "Databases"],
)


section_title("Professional intelligence", "🗄️")
render_action_grid(
    [
        ("pages/38_Data_Intelligence_Hub.py", "Data Intelligence Hub", "🗄️", "Unify trusted research data and metadata."),
        ("pages/39_Knowledge_Warehouse.py", "Knowledge Warehouse", "🧠", "Organise reusable scientific knowledge."),
        ("pages/40_Analytics_Observability.py", "Analytics & Observability", "📈", "Review analytics, signals and operations."),
        ("pages/41_Research_Assets.py", "Research Assets", "📚", "Browse curated project resources."),
        ("pages/42_Internet_Research_Hub.py", "Internet Research Hub", "🌐", "Start a traceable external research task."),
    ],
    key="quick_intelligence",
)

section_title("Choose your scientific starting point", "→")
render_action_grid(
    [
        ("pages/1_Sequence_Analyzer.py", "Analyse DNA / Protein", "🧬", "Inspect sequence quality and basic properties."),
        ("pages/3_Drug_SMILES_Analyzer.py", "Analyse a Drug", "💊", "Check a SMILES structure before modelling."),
        ("pages/5_Model_Training.py", "Train DTI Model", "🧠", "Configure a reproducible training run."),
        ("pages/6_DTI_Predictor.py", "Run Prediction", "🔬", "Score a supported drug–target input."),
        ("pages/20_Workflow_Dashboard.py", "Workflow Dashboard", "📍", "Continue tracked research work."),
        ("pages/21_Dataset_Registry_Lineage.py", "Register Dataset", "🧾", "Record dataset lineage and provenance."),
        ("pages/22_Model_Lifecycle.py", "Model Lifecycle", "🏷️", "Review model status and controls."),
        ("pages/23_Batch_Prediction_Jobs.py", "Resumable Batch Jobs", "⚙️", "Launch or resume managed batch work."),
    ],
    key="quick_science",
)

section_title("Portfolio, governance and evidence", "🛡️")
render_action_grid(
    [
        ("pages/27_Executive_Overview.py", "Executive Overview", "📈", "See programme-level progress at a glance."),
        ("pages/28_Project_Portfolio.py", "Project Portfolio", "📁", "Manage research projects and their context."),
        ("pages/29_Activity_Risk_Center.py", "Activity & Risk Center", "🔔", "Review work activity and captured risks."),
        ("pages/30_Governance_Hub.py", "Governance Hub", "🛡️", "Open governance controls and records."),
        ("pages/32_Release_Readiness_Lineage.py", "Release Readiness", "🧭", "Check evidence-linked release status."),
        ("pages/31_Evidence_Package_Studio.py", "Evidence Package Studio", "📦", "Prepare a traceable evidence package."),
    ],
    key="quick_governance",
)

section_title("Data and model toolkit", "🗃️")
render_action_grid(
    [
        ("pages/33_Data_Model_Library.py", "Data & Model Library", "🗃️", "Browse bundled resources and registered assets."),
        ("pages/5_Model_Training.py", "Train with Bundled Data", "🤖", "Start a model run with included examples."),
        ("pages/6_DTI_Predictor.py", "Use Pretrained Model", "🎯", "Open the prepared prediction workflow."),
        ("pages/23_Batch_Prediction_Jobs.py", "Run Batch Sample", "📦", "Try a structured batch workflow."),
        ("pages/34_ML_AutoLab.py", "ML AutoLab", "🧠", "Explore guided ML experiments."),
        ("pages/35_Double_Data_ML.py", "Double Data ML", "⚡", "Explore scaled data preparation workflows."),
        ("pages/36_Data_Coverage_Center.py", "Data Coverage Center", "🧰", "Inspect data coverage and gaps."),
        ("pages/37_5X_Data_ML.py", "5X Data ML", "🚀", "Open expanded data and ML utilities."),
    ],
    key="quick_data",
)

section_title("Workspace support", "🧰")
render_action_grid(
    [
        ("pages/25_Command_Center.py", "Command Center", "🎛️", "Review application-wide operational controls."),
        ("pages/26_Research_Report_Studio.py", "Report Studio", "📝", "Create a structured research report."),
        ("pages/18_Workspace_Backup_Restore.py", "Backup or Restore Workspace", "💾", "Manage local workspace backups safely."),
        ("pages/19_System_Diagnostics.py", "Check or Repair Setup", "🩺", "Run local diagnostic and repair checks."),
        ("pages/24_Appearance_Studio.py", "Appearance Studio", "🎨", "Tune the visual experience to your workflow."),
    ],
    key="quick_support",
)

st.divider()
section_title("Instant sequence check", "🧬")
example = st.selectbox(
    "Example",
    [
        "DNA",
        "Protein",
        "Paste my own",
    ],
)
defaults = {
    "DNA": ">quick_dna\nATGAAACCCGGGTTTAAATGCGTATCGATCGTACGATCGATGCTAGCTAGCTAA",
    "Protein": ">quick_protein\nMKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE",
    "Paste my own": "",
}
raw = st.text_area(
    "Sequence or FASTA",
    value=defaults[example],
    height=140,
)
if st.button("Run quick check", type="primary"):
    try:
        parsed = parse_sequence_text(raw)
        detection = detect_sequence_type(parsed.sequence)
        selected = detection.detected_type
        if selected not in {
            SequenceType.DNA,
            SequenceType.RNA,
            SequenceType.PROTEIN,
        }:
            raise ValueError(
                "Sequence type is ambiguous. Use the full Sequence Analyzer "
                "to select the type manually."
            )
        invalid = validate_for_type(parsed.sequence, selected)
        if invalid:
            raise ValueError("Sequence contains invalid symbols for the detected type.")
        if selected in {SequenceType.DNA, SequenceType.RNA}:
            result = nucleotide_statistics(
                parsed.sequence,
                is_rna=selected == SequenceType.RNA,
            )
            render_metric_board(
                [
                    ("Detected type", selected.value, "Inferred from the submitted sequence.", "info"),
                    ("Length", result["length"], "Total nucleotide symbols after parsing.", "neutral"),
                    ("GC content", f"{result['gc_percent']:.2f}%", "Descriptive composition only.", "success"),
                    ("Ambiguous symbols", result["ambiguous_count"], "Check these before downstream use.", "warning"),
                ]
            )
        else:
            result = protein_statistics(parsed.sequence)
            render_metric_board(
                [
                    ("Detected type", selected.value, "Inferred from the submitted sequence.", "info"),
                    ("Length", result["length"], "Total amino-acid symbols after parsing.", "neutral"),
                    (
                        "Molecular weight",
                        (
                            f"{result['molecular_weight']:.2f}"
                            if result.get("molecular_weight") is not None
                            else "Unavailable"
                        ),
                        "Calculated descriptive property.",
                        "success",
                    ),
                    (
                        "GRAVY",
                        (f"{result['gravy']:.3f}" if result.get("gravy") is not None else "Unavailable"),
                        "Calculated descriptive hydropathy index.",
                        "warning",
                    ),
                ]
            )
        st.download_button(
            "Download quick result JSON",
            json.dumps(result, indent=2, default=str),
            "quick_sequence_result.json",
            "application/json",
        )
    except Exception as exc:
        st.error(str(exc))

st.divider()
section_title("Ready-made templates", "⬇")
classification_template = pd.DataFrame(
    [
        {
            "drug_id": "DRUG_001",
            "canonical_smiles": "CCO",
            "target_id": "TARGET_001",
            "protein_sequence": "ACDEFGHIKLMNPQRSTVWY",
            "label": 1,
            "source": "replace_with_real_source",
        }
    ]
)
regression_template = pd.DataFrame(
    [
        {
            "drug_id": "DRUG_001",
            "canonical_smiles": "CCO",
            "target_id": "TARGET_001",
            "protein_sequence": "ACDEFGHIKLMNPQRSTVWY",
            "p_activity": 6.0,
            "activity_type": "IC50",
            "source": "replace_with_real_source",
        }
    ]
)
download_left, download_right = st.columns(2)
download_left.download_button(
    "Download classification CSV template",
    classification_template.to_csv(index=False),
    "dti_classification_template.csv",
    "text/csv",
    width="stretch",
)
download_right.download_button(
    "Download regression CSV template",
    regression_template.to_csv(index=False),
    "dti_regression_template.csv",
    "text/csv",
    width="stretch",
)

st.info(
    "Start with Sequence Analyzer for learning. "
    "For DTI, first audit the dataset, then train, evaluate and predict."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='quick_start', title='Quick Start', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
