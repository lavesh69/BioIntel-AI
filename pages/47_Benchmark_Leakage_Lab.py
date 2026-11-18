from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.training.leakage_audit import audit_train_test_leakage
from biointel.ui.components import smart_json
from biointel.ui.performance import read_csv_cached
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

st.set_page_config(page_title="Benchmark & Leakage Lab · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("leakage_lab", key_prefix="step116_47_Benchmark_Leakage_Lab_leakage_lab_1", expanded=False)
hero("🧪 Benchmark & Leakage Lab", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption("Detect compound, Bemis–Murcko scaffold, exact target, target-cluster and drug–target pair leakage before claiming external performance.")

input_mode = st.radio(
    "Benchmark input",
    ["Preloaded leakage-safe demonstration", "Upload train/test CSV files"],
    horizontal=True,
)
train = test = None
if input_mode == "Preloaded leakage-safe demonstration":
    demo_dir = ROOT / "data" / "examples" / "demo_workspace"
    train = read_csv_cached(demo_dir / "demo_leakage_train.csv", low_memory=False)
    test = read_csv_cached(demo_dir / "demo_leakage_test.csv", low_memory=False)
    st.warning("Preloaded data demonstrate the audit only; they are not a scientific benchmark.")
    left_preview, right_preview = st.columns(2)
    left_preview.dataframe(train, width="stretch", hide_index=True)
    right_preview.dataframe(test, width="stretch", hide_index=True)
else:
    train_upload = st.file_uploader("Training CSV", type=["csv"], key="leak_train")
    test_upload = st.file_uploader("Independent test/benchmark CSV", type=["csv"], key="leak_test")
    render_upload_preflight(
        train_upload, key="leak_train", allowed_extensions=["csv"], soft_limit_mb=50, hard_limit_mb=250
    )
    render_upload_preflight(
        test_upload, key="leak_test", allowed_extensions=["csv"], soft_limit_mb=50, hard_limit_mb=250
    )
    if train_upload and test_upload:
        try:
            train = read_uploaded_table(train_upload, low_memory=False)
            test = read_uploaded_table(test_upload, low_memory=False)
        except Exception as exc:
            st.error(str(exc))

if train is not None and test is not None:
    try:
        shared = sorted(set(train.columns) & set(test.columns))
        smiles = st.selectbox("SMILES column", shared, index=shared.index("canonical_smiles") if "canonical_smiles" in shared else 0)
        sequence = st.selectbox("Protein sequence column", shared, index=shared.index("protein_sequence") if "protein_sequence" in shared else min(1, len(shared)-1))
        cluster_options = ["Automatic prefix cluster", *shared]
        cluster = st.selectbox("Target cluster column", cluster_options)
        if st.button("Run strict leakage audit", type="primary"):
            result = audit_train_test_leakage(train, test, smiles_column=smiles, sequence_column=sequence, target_cluster_column=None if cluster.startswith("Automatic") else cluster)
            st.session_state["step25_leakage"] = asdict(result)
    except Exception as exc:
        st.error(str(exc))

result = st.session_state.get("step25_leakage")
if result:
    st.success("Leakage audit passed." if result["passed"] else "Leakage detected. Scientific release must remain blocked.")
    cols = st.columns(5)
    for col, key in zip(cols, ("exact_compound_overlap","scaffold_overlap","exact_target_overlap","target_cluster_overlap","pair_overlap")):
        col.metric(key.replace("_"," ").title(), result[key])
    smart_json(result)
    st.download_button("Download leakage audit", json.dumps(result, indent=2), "step25_leakage_audit.json", "application/json")
else:
    st.info("Upload separate training and independent benchmark datasets.")

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("benchmark_leakage", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
