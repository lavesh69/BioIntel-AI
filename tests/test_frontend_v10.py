from __future__ import annotations

from biointel.ui.frontend_v10 import CAPABILITIES, FRONTEND_V10_CSS, Capability, icon_for_kicker


def test_frontend_v10_has_all_primary_product_profiles() -> None:
    required = {
        "connect", "shiro", "studio", "home", "classroom", "pulse", "academy",
        "universe", "examinations", "intelligence", "institution", "visuals", "desktop",
    }
    assert required <= set(CAPABILITIES)
    assert all(len(CAPABILITIES[key]) == 4 for key in required)
    assert all(isinstance(item, Capability) for key in required for item in CAPABILITIES[key])


def test_frontend_v10_covers_complete_streamlit_surface() -> None:
    required_tokens = {
        "Phase 10 full frontend completion",
        "stChatMessage", "stChatInput", "stDataFrame", "stDataEditor", "stFileUploader",
        "stPlotlyChart", "stVegaLiteChart", "stForm", "stMetric", "stPageLink",
        "bx10-compact-hero", "bx10-capability-grid", "bx10-kpi-grid", "bx10-action-grid",
        "bx10-empty", "bx10-timeline", "bx10-section-head", "bx10-avatar",
    }
    assert required_tokens <= {token for token in required_tokens if token in FRONTEND_V10_CSS}


def test_kicker_icons_are_deterministic() -> None:
    assert icon_for_kicker("DISCOVER") == "⌕"
    assert icon_for_kicker("validate") == "✓"
    assert icon_for_kicker("unknown") == "◆"
