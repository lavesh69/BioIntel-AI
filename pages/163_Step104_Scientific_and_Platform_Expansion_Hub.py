from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from biointel.nextgen.catalog import NEXTGEN_MODULES, PLATFORM_MODULES, SCIENTIFIC_MODULES
from biointel.ui.components import metric_cards
from biointel.ui.theme import apply_theme, section_title
from biointel.ui.workbench import compact_module_header

st.set_page_config(page_title="Scientific Platform Services · BioIntel AI", page_icon="🚀", layout="wide")
apply_theme()
compact_module_header(
    title="Scientific Platform Services",
    summary="Launch advanced scientific workspaces and hardened platform services with bounded local processing, persistent state and explicit evidence boundaries.",
    icon="🚀",
    category="Scientific Platform",
    tags=(f"{len(SCIENTIFIC_MODULES)} scientific tools", f"{len(PLATFORM_MODULES)} platform services", "Persistent local state"),
    boundary="Local implementation readiness does not replace independent scientific validation, specialist external software, current reference databases or regulated operating evidence.",
)
metric_cards(
    [
        ("Scientific workspaces", len(SCIENTIFIC_MODULES), "Advanced analytical tools"),
        ("Platform services", len(PLATFORM_MODULES), "Shared infrastructure"),
        ("Integrated capabilities", len(NEXTGEN_MODULES), "Searchable and connected"),
        ("Execution boundary", "Local", "No silent external tools"),
    ]
)
for kind, modules in [("Scientific workspaces", SCIENTIFIC_MODULES), ("Platform services", PLATFORM_MODULES)]:
    section_title(kind, "🧬" if kind.startswith("Scientific") else "⚙️")
    for start in range(0, len(modules), 3):
        columns = st.columns(3)
        for column, module in zip(columns, modules[start : start + 3], strict=False):
            with column:
                with st.container(border=True):
                    st.markdown(f"### {module.icon} {module.title}")
                    st.caption(module.category)
                    st.write(module.summary)
                    page_file = next(
                        page
                        for page in Path(__file__).parent.glob(f"{module.page_number}_*.py")
                        if page.name != Path(__file__).name
                    )
                    st.page_link(f"pages/{page_file.name}", label="Open workspace", width="stretch")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='step104_expansion_hub', title='Scientific Platform Services', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
