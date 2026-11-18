from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_scientific_v135 import build_module_scientific_artifacts
from biointel.nextgen.native_execution_v136 import profile_table

ROOT = Path(__file__).resolve().parents[1]


def _drawable(figure: object) -> bool:
    traces = tuple(getattr(figure, "data", ()) or ())
    layout = getattr(figure, "layout", None)
    annotations = tuple(getattr(layout, "annotations", ()) or ()) if layout is not None else ()
    images = tuple(getattr(layout, "images", ()) or ()) if layout is not None else ()
    shapes = tuple(getattr(layout, "shapes", ()) or ()) if layout is not None else ()
    return bool(traces or annotations or images or shapes)


def test_all_fifteen_biomedical_modules_produce_nonempty_tables_and_drawable_visuals() -> None:
    visual_count = 0
    table_count = 0
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        module = MODULE_BY_KEY[key]
        data = demo_frame(module, 120)
        result, _summary, secondary, extras = analyse(data, module, 0.70)
        artifacts = build_module_scientific_artifacts(key, data, result, secondary, extras)
        assert artifacts["summary"].get("safe_error") is None, key
        assert artifacts["tables"], key
        assert artifacts["figures"], key
        for name, table in artifacts["tables"].items():
            assert isinstance(table, pd.DataFrame), f"{key}:{name}"
            assert not table.empty, f"{key}:{name}"
            table_count += 1
        for name, figure in artifacts["figures"].items():
            assert _drawable(figure), f"{key}:{name}"
            visual_count += 1
    assert table_count >= 35
    assert visual_count >= 45


def test_native_pipeline_profile_table_is_arrow_safe_and_homogeneous() -> None:
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        table = profile_table(key)
        assert not table.empty
        assert table["Stage"].map(type).eq(str).all(), key
        assert table["Built-in stage"].map(type).eq(str).all(), key
        assert table["Execution"].map(type).eq(str).all(), key


def test_native_execution_uses_current_streamlit_width_api() -> None:
    source = (ROOT / "src/biointel/nextgen/native_execution_v136.py").read_text(encoding="utf-8")
    assert "use_container_width" not in source
    assert 'width="stretch"' in source


def test_chart_card_replaces_truly_blank_figures_with_bounded_no_data_state() -> None:
    source = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    assert "figure_empty = False" in source
    assert "No plottable chart data is available" in source
    assert 'expanded=figure_empty' in source


def test_shell_and_icon_guards_cover_popovers_metrics_buttons_and_expanders() -> None:
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css = (ROOT / "src/biointel/ui/desktop_ux.css").read_text(encoding="utf-8")
    assert "[1.00, 1.62, 1.78]" in theme
    for selector in (
        '[data-testid="stPopover"]>button svg',
        '[data-testid="stExpander"] summary svg',
        '[data-testid="stMetric"] [data-testid="stTooltipIcon"]',
        '[data-testid="stPlotlyChart"]',
        '[data-testid="stDataFrame"]',
    ):
        assert selector in css
