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

from biointel.authenticity_v162 import (  # noqa: E402
    legacy_model_authenticity,
    portfolio_authenticity_matrix,
    portfolio_authenticity_summary,
    provider_contract_matrix,
    verify_public_benchmark_suite,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title  # noqa: E402

st.set_page_config(page_title="Model Authenticity · BioIntel AI", page_icon="MA", layout="wide")
apply_theme()
hero(
    "Model Authenticity & Evidence Center",
    "Audit real public-data benchmark models, synthetic-model quarantine, immutable model packages, provider source contracts and domain-release blockers.",
    eyebrow="BioIntel AI · Step 162 Authentic Models & Evidence",
    chips=["5 public-data models", "Synthetic quarantine", "Immutable SHA-256", "Untouched holdouts", "Fail-closed release"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="Step 162 authenticates the source, snapshot, split, artifact and measured benchmark behaviour. Public benchmark authenticity is not the same as domain, clinical, wet-lab or regulatory validation.",
)


@st.cache_data(ttl=120, show_spinner=False)
def _benchmarks() -> pd.DataFrame:
    return verify_public_benchmark_suite(ROOT)


@st.cache_data(ttl=120, show_spinner=False)
def _legacy() -> pd.DataFrame:
    return legacy_model_authenticity(ROOT)


@st.cache_data(ttl=120, show_spinner=False)
def _providers() -> pd.DataFrame:
    return provider_contract_matrix(ROOT)


@st.cache_data(ttl=120, show_spinner=False)
def _modules() -> pd.DataFrame:
    return portfolio_authenticity_matrix(ROOT)


benchmarks = _benchmarks()
legacy = _legacy()
providers = _providers()
modules = _modules()
summary = portfolio_authenticity_summary(modules)
metric_cards(
    [
        ("Verified public models", f"{int(benchmarks['passed'].astype(bool).sum())}/{len(benchmarks)}", "Real public datasets + holdouts"),
        ("Synthetic models quarantined", int(legacy["synthetic_demo"].astype(bool).sum()) if not legacy.empty else 0, "Demo-only, not scientific defaults"),
        ("Provider source contracts", f"{int(providers['source_descriptor_verified'].astype(bool).sum())}/{len(providers)}", "Official-source descriptors"),
        ("Domain-release eligible", summary.get("domain_model_release_eligible", 0), "Requires external/domain evidence"),
    ]
)

section_title("Authentic public benchmark suite", "✓")
smart_dataframe(benchmarks, height=320, key="step162_benchmarks")
st.caption("Each model package contains an immutable dataset snapshot, deterministic train/calibration/holdout split, untouched holdout predictions, calibration or conformal diagnostics, model card, environment record and SHA-256 file manifest.")

section_title("Legacy model authenticity registry", "🛡️")
legacy_view = legacy.copy()
if not legacy_view.empty:
    state = st.selectbox(
        "Authenticity state",
        ["All"] + sorted(legacy_view["authenticity_state"].dropna().astype(str).unique().tolist()),
        key="step162_legacy_state",
    )
    if state != "All":
        legacy_view = legacy_view.loc[legacy_view["authenticity_state"] == state]
smart_dataframe(legacy_view, height=520, key="step162_legacy_registry")

section_title("Scientific source contracts", "🔗")
smart_dataframe(providers, height=430, key="step162_provider_contracts")
st.caption("A verified source descriptor or checksummed local seed does not automatically qualify a complete provider release. Licence acceptance, release identity, full record QC and scientific review remain mandatory.")

section_title("All-module authenticity matrix", "🧬")
view = st.selectbox(
    "Module view",
    ["All modules", "Specialist runtimes missing", "Production references missing", "Lowest practical readiness"],
    key="step162_module_filter",
)
visible = modules.copy()
if view == "Specialist runtimes missing":
    visible = visible.loc[visible["specialist_engines_installed"] < visible["specialist_engines_required"]]
elif view == "Production references missing":
    visible = visible.loc[visible["production_references_qualified"] < visible["production_references_required"]]
elif view == "Lowest practical readiness":
    visible = visible.sort_values(["practical_scientific_readiness_score", "title"]).head(25)
smart_dataframe(visible, height=620, key="step162_module_matrix")
st.download_button(
    "Download Step 162 module authenticity matrix",
    modules.to_csv(index=False).encode("utf-8"),
    "biointel_step162_module_authenticity_matrix.csv",
    "text/csv",
    width="stretch",
)

with st.expander("Exact meaning of authentic", expanded=False):
    smart_json(
        {
            "verified_in_step162": [
                "Public/non-synthetic dataset snapshot",
                "Dataset and model artifact SHA-256 bindings",
                "Deterministic split manifest",
                "Untouched holdout predictions and measured metrics",
                "Calibration or conformal uncertainty diagnostics",
                "Model card, limitations and intended-use statement",
                "Synthetic legacy model quarantine",
            ],
            "not_claimed": [
                "Independent hospital/laboratory validation",
                "Wet-lab confirmation",
                "Clinical effectiveness",
                "Regulatory approval",
                "Fitness for a different scientific domain",
            ],
        },
        title="Step 162 authenticity policy",
        key="step162_policy",
    )
    st.download_button(
        "Download summary JSON",
        json.dumps(summary, indent=2).encode("utf-8"),
        "biointel_step162_authenticity_summary.json",
        "application/json",
        width="stretch",
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
