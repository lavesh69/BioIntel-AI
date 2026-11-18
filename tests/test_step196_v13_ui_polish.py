from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v16_five_part_contract_and_visual_components_are_present() -> None:
    component = (ROOT / "src" / "biointel" / "ui" / "visual_polish.py").read_text(encoding="utf-8")
    aesthetic = (ROOT / "src" / "biointel" / "ui" / "aesthetic.py").read_text(encoding="utf-8")
    release = json.loads((ROOT / "STEP196_RELEASE.json").read_text(encoding="utf-8"))

    assert release["package_revision"] == "V16-5PART"
    assert release["part_count"] == 5
    assert release["ui_polish_upgrade"]["visual_state_is_not_evidence"] is True
    assert "def render_metric_board" in component
    assert "def render_action_grid" in component
    assert "grid-template-columns:repeat(auto-fit" in component
    assert ':has(> [data-testid="stColumn"]:nth-child(5))' in aesthetic


def test_v16_upgraded_command_centers_use_shared_visual_hierarchy() -> None:
    for name in (
        "259_Step189_Universal_Production_Platform_Center.py",
        "260_Step190_Scientific_Execution_Interoperability_Center.py",
        "262_Step193_Mandatory_Module_Completion_Install_Repair_Center.py",
    ):
        source = (ROOT / "pages" / name).read_text(encoding="utf-8")
        assert "apply_theme()" in source
        assert "hero(" in source
        assert "scientific_boundary_banner(" in source
        assert "render_metric_board(" in source
        assert "smart_dataframe(" in source


def test_v16_quick_start_uses_responsive_actions_instead_of_cramped_link_rows() -> None:
    source = (ROOT / "pages" / "0_Quick_Start.py").read_text(encoding="utf-8")
    assert "render_action_grid(" in source
    assert "render_metric_board(" in source
    assert "st.columns(8)" not in source
    assert "st.columns(5)" not in source
