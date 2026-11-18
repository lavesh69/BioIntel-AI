from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.evidence_registry import (
    registry_summary,
    seed_standard_licenses,
)
from biointel.data.real_evidence import import_curated_evidence, result_dict
from biointel.integrations.bindingdb import bindingdb_to_activity_frame
from biointel.integrations.chembl_evidence import download_activity_evidence
from biointel.integrations.pubchem_bioassay import pubchem_activity_export_to_frame
from biointel.ui.components import smart_json
from biointel.ui.performance import read_csv_cached
from biointel.step121.panels import render_real_evidence_upgrade
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

st.set_page_config(page_title="Real Evidence Studio · BioIntel AI", page_icon="🧾", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("real_evidence", key_prefix="step116_46_Real_Evidence_Studio_real_evidence_1", expanded=False)
hero("🧾 Real Evidence Studio", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption("Import real experimental activity evidence with standardization, licences, row provenance, review status and canonical dataset-hash binding.")

EVIDENCE_DB = ROOT / "reports" / "evidence.sqlite3"
DATASET_DB = ROOT / "reports" / "datasets.sqlite3"
OUTPUT = ROOT / "data" / "real_evidence"
seed_standard_licenses(EVIDENCE_DB)

upload_tab, chembl_tab, manifest_tab = st.tabs(["File import", "Live ChEMBL intake", "Latest manifest"])

with upload_tab:
    demo_file = ROOT / "data" / "examples" / "demo_workspace" / "BioIntel_Demo_Activity_Data.csv"
    st.info(
        "A preloaded demonstration evidence pack is already available in the registry. "
        "Use the upload controls below only for your own real source files."
    )
    demo_preview = read_csv_cached(demo_file, low_memory=False)
    st.dataframe(demo_preview, width="stretch", hide_index=True)
    st.download_button(
        "Download demonstration evidence template",
        demo_file.read_bytes(),
        demo_file.name,
        "text/csv",
    )
    st.divider()
    provider = st.selectbox("Provider format", ["generic", "bindingdb", "pubchem_bioassay"])
    source_release = st.text_input("Source release/version", value="user_import")
    uploaded = st.file_uploader("Evidence file", type=["csv", "tsv", "txt"])
    render_upload_preflight(
        uploaded,
        key="real_evidence",
        allowed_extensions=["csv", "tsv", "txt"],
        soft_limit_mb=50,
        hard_limit_mb=250,
    )
    active_threshold = st.slider("Active pActivity threshold", 4.0, 10.0, 6.0, 0.25)
    if uploaded is not None:
        try:
            suffix = Path(uploaded.name).suffix.lower()
            if provider == "bindingdb":
                temp = OUTPUT / "_uploaded_bindingdb.tsv"
                OUTPUT.mkdir(parents=True, exist_ok=True)
                temp.write_bytes(uploaded.getvalue())
                source = bindingdb_to_activity_frame(temp)
            else:
                source = read_uploaded_table(uploaded, low_memory=False)
                if provider == "pubchem_bioassay":
                    source = pubchem_activity_export_to_frame(source)
            st.dataframe(source.head(100), width="stretch", hide_index=True)
            if st.button("Curate and register evidence", type="primary"):
                result = import_curated_evidence(
                    source,
                    provider=provider,
                    source_release=source_release.strip() or None,
                    registry_path=EVIDENCE_DB,
                    dataset_registry_path=DATASET_DB,
                    output_directory=OUTPUT,
                    active_threshold=active_threshold,
                    metadata={"uploaded_filename": uploaded.name},
                )
                st.session_state["step25_import_result"] = result_dict(result)
        except Exception as exc:
            st.error(str(exc))

with chembl_tab:
    st.warning("Live intake requires internet and respects official ChEMBL/UniProt service availability. Imported rows remain review-pending.")
    target_id = st.text_input("Target ChEMBL ID", placeholder="CHEMBL203")
    max_rows = st.number_input("Maximum activity rows", min_value=10, max_value=2000, value=100, step=10)
    release = st.text_input("ChEMBL release label", value="live_api", key="chembl_release")
    if st.button("Fetch, curate and register ChEMBL evidence"):
        try:
            frame = download_activity_evidence(target_chembl_id=target_id.strip() or None, maximum_rows=int(max_rows))
            if frame.empty:
                st.warning("No activity rows were returned.")
            else:
                result = import_curated_evidence(
                    frame,
                    provider="chembl",
                    source_release=release.strip() or "live_api",
                    registry_path=EVIDENCE_DB,
                    dataset_registry_path=DATASET_DB,
                    output_directory=OUTPUT,
                    source_homepage="https://www.ebi.ac.uk/chembl/",
                    active_threshold=6.0,
                    metadata={"target_chembl_id": target_id.strip() or None, "live_api": True},
                )
                st.session_state["step25_import_result"] = result_dict(result)
        except Exception as exc:
            st.error(str(exc))

with manifest_tab:
    result = st.session_state.get("step25_import_result")
    if result:
        st.success("Evidence imported. Scientific release remains blocked until all rows are reviewed and accepted.")
        smart_json(result)
        st.download_button("Download evidence manifest", json.dumps(result["manifest"], indent=2), "step25_evidence_manifest.json", "application/json")
    else:
        demo_manifest = ROOT / "data" / "examples" / "demo_workspace" / "demo_evidence_manifest.json"
        if demo_manifest.is_file():
            payload = json.loads(demo_manifest.read_text(encoding="utf-8"))
            st.warning("Showing the preloaded demonstration manifest. It is not real experimental evidence.")
            smart_json(payload)
            st.download_button(
                "Download demonstration manifest",
                demo_manifest.read_bytes(),
                demo_manifest.name,
                "application/json",
            )
        st.subheader("Evidence registry overview")
        smart_json(registry_summary(EVIDENCE_DB))
render_real_evidence_upgrade(key_prefix="step121_real_evidence")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='real_evidence_studio', title='Real Evidence Studio', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
