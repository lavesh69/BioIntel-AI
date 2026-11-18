from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.quality.model_audit import audit_model_directory
from biointel.training.model_artifact import (
    discover_model_artifact_candidates,
    load_model_artifact_cached,
)
from biointel.training.release_gate import evaluate_release_gate
from biointel.ui.brand import branded_model_label_from_sidecar
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="Scientific Release Gate · BioIntel AI", page_icon="🛡️", layout="wide")
apply_theme()
hero(
    "🛡️ Scientific Model Release Gate",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption(
    "Block scientific release when training data are synthetic, external validation is missing, "
    "performance is below policy or leakage-safe split evidence is absent."
)

models, incompatible_models = discover_model_artifact_candidates(ROOT / "models")
if incompatible_models:
    st.caption(
        f"Excluded {len(incompatible_models)} incompatible benchmark/model file(s) from this workflow."
    )
if not models:
    st.error("No local model artifacts are available.")
    st.stop()
model_audit = audit_model_directory(ROOT / "models")
audit_by_model = {item["model_file"]: item for item in model_audit["models"]}
selected = st.selectbox(
    "Model artifact",
    models,
    format_func=lambda path: branded_model_label_from_sidecar(
        path, audit_by_model.get(path.name, {})
    ),
)
external_upload = st.file_uploader(
    "External validation report JSON (optional)", type=["json"], key="release_external"
)
split_upload = st.file_uploader("Leakage/split audit JSON", type=["json"], key="release_split")
evidence_upload = st.file_uploader(
    "Quality-Hardened evidence manifest JSON", type=["json"], key="release_evidence"
)
render_upload_preflight(
    external_upload,
    key="release_external",
    allowed_extensions=["json"],
    soft_limit_mb=2,
    hard_limit_mb=10,
)
render_upload_preflight(
    split_upload,
    key="release_split",
    allowed_extensions=["json"],
    soft_limit_mb=2,
    hard_limit_mb=10,
)
render_upload_preflight(
    evidence_upload,
    key="release_evidence",
    allowed_extensions=["json"],
    soft_limit_mb=2,
    hard_limit_mb=10,
)


def read_json(uploaded):
    if uploaded is None:
        return None
    return json.loads(io.BytesIO(uploaded.getvalue()).read().decode("utf-8"))


if st.button("Evaluate release gate", type="primary"):
    try:
        artifact = load_model_artifact_cached(selected, trusted_root=ROOT / "models")
        external = read_json(external_upload)
        split = read_json(split_upload)
        evidence_manifest = read_json(evidence_upload)
        result = evaluate_release_gate(
            metadata=artifact.metadata,
            external_validation=external,
            split_summary=split,
            evidence_manifest=evidence_manifest,
        )
    except Exception as exc:
        st.error(str(exc))
    else:
        st.session_state["release_gate_result"] = result

result = st.session_state.get("release_gate_result")
if result is not None:
    left, middle, right = st.columns(3)
    left.metric("Release decision", "PASS" if result.passed else "BLOCKED")
    middle.metric("Gate score", f"{result.score:.1f}%")
    right.metric("Blockers", len(result.blockers))
    if result.passed:
        st.success("All blocking scientific release controls passed.")
    else:
        for blocker in result.blockers:
            st.error(blocker)
    for warning in result.warnings:
        st.warning(warning)
    st.dataframe(result.checks, width="stretch", hide_index=True)
    st.download_button(
        "Download release-gate evidence",
        json.dumps(asdict(result), indent=2, default=str),
        selected.stem + "_release_gate.json",
        "application/json",
    )

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("release_gate", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
