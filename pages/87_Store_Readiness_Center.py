from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.release import build_store_readiness  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="Store Readiness · BioIntel AI", page_icon="📦", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('store_readiness_core', expanded=False)

hero(
    "Store Readiness Center",
    "One release view for web hosting, Google Play, Apple App Store and Microsoft Store packaging.",
    eyebrow="BioIntel AI · Cross-platform release candidate",
    chips=["Android App Bundle", "iOS Xcode project", "Windows MSIX/AppX", "Hosted web deployment"],
)

readiness = build_store_readiness(ROOT)
percent = readiness["repository_readiness_percent"]
if percent == 100:
    badge("● Repository-side store preparation complete", "success")
else:
    badge(f"● Repository-side preparation {percent:.1f}%", "warning")

st.metric("Release version", readiness["version"])
st.progress(percent / 100.0, text=f"Repository checks: {readiness['repository_ready_count']}/{readiness['repository_check_count']}")
st.dataframe(
    [{"check": key.replace("_", " ").title(), "ready": value} for key, value in readiness["repository_checks"].items()],
    width="stretch",
    hide_index=True,
    column_config={"ready": st.column_config.CheckboxColumn("Ready")},
)

section_title("External submission requirements", "⚠")
for blocker in readiness["external_blockers"]:
    st.markdown(f"- {blocker}")
insight_callout("Truthful release boundary", readiness["truthful_status"], tone="warning")

section_title("Build entry points", "⌘")
st.code(
    """# Validate repository release readiness
python scripts/verify_store_release.py

# Mobile shell
cd platform/mobile
npm ci
npm run build
npx cap sync

# Windows local desktop build (run on Windows)
powershell -ExecutionPolicy Bypass -File scripts/store/build_windows_release.ps1

# Signed multi-store release
Use .github/workflows/store-release.yml with your store identities and signing secrets.
""",
    language="bash",
)

st.caption("Store approval is decided by Google, Apple and Microsoft after account, signing, listing and review requirements are satisfied.")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("store_readiness_core", None, key_prefix="step114_store_readiness_core", expanded=False)

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("store_readiness_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("store_readiness_core", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("store_readiness_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('store_readiness_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('store_readiness_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('store_readiness_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('store_readiness_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('store_readiness_core', expanded=False)

