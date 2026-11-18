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

from biointel.external_v172 import ALL_MODULES, PROFILES, Step172Registry, profile_matrix  # noqa: E402
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.operational_canvas import render_operational_canvas  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="External Confirmation & Formal Release · BioIntel AI", page_icon="✅", layout="wide")
apply_theme()
registry = Step172Registry(ROOT)
matrix = registry.matrix(refresh=False)

hero(
    "External Confirmation & Formal Release Qualification",
    "Qualify wet-lab, prospective and orthogonal confirmation, expert sign-off, physical instrument/site testing, operating history and formal release decisions without inferring evidence that does not exist.",
    eyebrow="Step 172 · cryptographic evidence intake · fail-closed controlled release",
    chips=["80 module profiles", "SHA-256 evidence", "Detached signature verification", "Formal release quorum"],
)
scientific_boundary_banner(
    source_kind="external_evidence",
    release_eligible=bool(matrix["release_eligible"].any()) if not matrix.empty else False,
    message=(
        "Step 172 provides a complete qualification system. It does not create laboratory results, expert identities, site accreditation, "
        "instrument qualification, prospective outcomes or release approvals. Only imported checksum-valid evidence can unlock a module."
    ),
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Framework coverage", "80/80")
m2.metric("Software framework", "10/10")
m3.metric("Evidence packages found", int((matrix["manifest_sha256"].astype(str) != "").sum()) if not matrix.empty else 0)
m4.metric("Controlled-release eligible", int(matrix["release_eligible"].sum()) if not matrix.empty else 0)

requirements_tab, matrix_tab, submission_tab, physical_tab, governance_tab = st.tabs([
    "Module requirements", "Qualification matrix", "Prepare/import evidence", "Physical qualification", "Release governance"
])

with requirements_tab:
    section_title("Evidence requirements by module", "🧾")
    profile = profile_matrix()
    smart_dataframe(profile, height=640, key="step172_profiles")

with matrix_tab:
    section_title("Current fail-closed qualification state", "🚦")
    smart_dataframe(matrix, height=680, key="step172_matrix")
    st.download_button("Download qualification matrix", matrix.to_csv(index=False).encode(), "step172_external_confirmation_matrix.csv", "text/csv")

with submission_tab:
    module_key = st.selectbox("Module", ALL_MODULES, format_func=lambda key: f"{PROFILES[key].module_title} · {key}")
    module_dir = ROOT / "data" / "step172" / "module_packages" / module_key
    target = registry.submissions / module_key
    c1, c2 = st.columns(2)
    if c1.button("Prepare submission workspace", type="primary"):
        import shutil
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(module_dir, target)
        shutil.copy2(target / "confirmation_manifest_template.json", target / "confirmation_manifest.json")
        st.success(f"Prepared: {target}")
    if c2.button("Evaluate current submission"):
        result = registry.import_submission(module_key, actor="streamlit-operator")
        render_operational_canvas(
            "Submission evaluation",
            result,
            workflow=("Evidence package", "Checksum verification", "Gate evaluation", "Release decision"),
            empty_message="No submission evaluation is available yet.",
        )
    st.code(str(registry.submission_path(module_key)), language="text")
    st.caption("Place actual evidence files beside the manifest, update relative paths and SHA-256 values, then evaluate. Self-declared booleans without verified files do not pass.")

with physical_tab:
    section_title("Target-machine and instrument qualification", "🖥️")
    insight_callout(
        "Run on the actual machine and site",
        "RUN_STEP172_PHYSICAL_QUALIFICATION_WINDOWS.bat records Windows, process, file-integrity and recovery probes. Antivirus, sleep/resume, network-loss and instrument tests require explicit target-site execution and evidence.",
        tone="warning",
    )
    st.code("RUN_STEP172_PHYSICAL_QUALIFICATION_WINDOWS.bat --instrument-tested --sleep-resume-tested --antivirus-tested --network-loss-tested", language="bat")
    report = ROOT / "reports" / "step172_physical_qualification.json"
    if report.exists():
        render_operational_canvas(
            "Physical qualification status",
            json.loads(report.read_text(encoding="utf-8")),
            workflow=("Host probe", "Recovery checks", "Evidence capture", "Qualification review"),
        )

with governance_tab:
    section_title("Formal release controls", "🛡️")
    smart_dataframe(pd.DataFrame([
        {"Control": "Independent domain expert", "Requirement": "Credential, conflict disclosure, signed review and detached cryptographic signature"},
        {"Control": "Independent quality approval", "Requirement": "QA approval recorded in the release decision"},
        {"Control": "Release quorum", "Requirement": "At least three named decision participants"},
        {"Control": "Intended-use boundary", "Requirement": "Approved intended use and prohibited uses are documented"},
        {"Control": "Risk acceptance", "Requirement": "Known residual risks and mitigations are formally accepted"},
        {"Control": "Upstream qualification", "Requirement": "Step 170 runtimes/references and Step 171 model benchmark where applicable"},
    ]), height=360, key="step172_governance")
    st.caption("Detached signatures are verified with OpenSSL SHA-256. This capability does not automatically establish organization-specific electronic-record regulatory compliance.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
