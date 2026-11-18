from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import plotly.express as px

from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.visual_workspace import (
    ACCESSIBILITY_PRESETS,
    apply_accessibility_preset,
    build_visual_report_bundle,
    delete_view,
    list_annotations,
    list_views,
    save_annotation,
    save_view,
    visual_text_summary,
)

ROOT = Path(__file__).resolve().parents[1]


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample": ["S1", "S2", "S3", "S4"],
            "score": [0.1, 0.8, 0.4, 0.9],
            "group": ["control", "treated", "control", "treated"],
        }
    )


def test_accessibility_presets_preserve_visual_data() -> None:
    frame = _frame()
    figure = px.scatter(frame, x="sample", y="score", color="group")
    assert len(ACCESSIBILITY_PRESETS) == 4
    for preset in ACCESSIBILITY_PRESETS:
        transformed = apply_accessibility_preset(figure, preset)
        assert len(transformed.data) == len(figure.data)
        assert transformed.to_dict()["data"]


def test_visual_workspace_persists_views_and_annotations(tmp_path: Path) -> None:
    database = tmp_path / "visual.sqlite3"
    view_id = save_view(
        name="Candidate review",
        module_key="dti_validation",
        chart_key="candidate_chart",
        title="Candidate evidence",
        evidence_status="external_validation",
        configuration={"selected_rows": [1, 3], "preset": "High contrast"},
        path=database,
    )
    annotation_id = save_annotation(
        module_key="dti_validation",
        chart_key="candidate_chart",
        visual_title="Candidate evidence",
        note="Confirm the leading candidate against the independent cohort.",
        selected_rows=[1, 3],
        path=database,
    )
    views = list_views("dti_validation", database)
    annotations = list_annotations("dti_validation", "candidate_chart", database)
    assert view_id in set(views["view_id"])
    assert annotation_id in set(annotations["annotation_id"])
    assert delete_view(view_id, database)
    assert list_views("dti_validation", database).empty


def test_visual_report_bundle_contains_reproducible_formats() -> None:
    frame = _frame()
    figure = px.scatter(frame, x="score", y="sample", color="group")
    bundle = build_visual_report_bundle(
        title="Candidate review",
        interpretation="Compares candidate scores across groups.",
        method="Exploratory score comparison",
        units="Score",
        evidence_status="external_validation",
        figure=figure,
        data=frame,
        configuration={"module_key": "dti_validation"},
    )
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = set(archive.namelist())
        assert {
            "visual/interactive_chart.html",
            "visual/figure.json",
            "data/displayed_records.csv",
            "report/visual_report.pdf",
            "report/visual_report.docx",
            "report/visual_report.pptx",
            "manifest.json",
        } <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema"] == "biointel.visual-report.v1"


def test_visual_summary_is_deterministic_and_informative() -> None:
    summary = visual_text_summary(_frame(), "Candidate review")
    assert "4 displayed record" in summary
    assert "median" in summary
    assert "most frequent" in summary.lower()


def test_visual_interaction_workspace_is_registered() -> None:
    page = PAGE_BY_KEY["visual_interaction_workspace"]
    assert page.path == "pages/164_Visual_Interaction_Accessibility_Workspace.py"
    page_text = (ROOT / page.path).read_text(encoding="utf-8")
    assert "Saved visual configurations" in page_text
    assert "Persistent visual annotations" in page_text
    assert "Safe visual diagnostics" in page_text


def test_shared_chart_card_includes_interaction_and_accessibility_controls() -> None:
    components = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    for token in (
        "Visual accessibility",
        "Linked selection",
        "Statistical context and provenance",
        "Save annotation",
        "Prepare report bundle",
        "Download complete visual report ZIP",
    ):
        assert token in components
    workspace = (ROOT / "src/biointel/ui/visual_workspace.py").read_text(encoding="utf-8")
    assert "Source status not declared" in workspace
    assert 'on_select="rerun"' in components
    assert 'selection_mode=("points", "box", "lasso")' in components


def test_scientific_and_decision_visual_suites_offer_comparison_mode() -> None:
    scientific = (ROOT / "src/biointel/ui/scientific_visuals.py").read_text(encoding="utf-8")
    decision = (ROOT / "src/biointel/ui/phase108_visuals.py").read_text(encoding="utf-8")
    for text in (scientific, decision):
        assert "Compare two visuals" in text
        assert "Single visual" in text
        assert "st.columns(2" in text


def test_global_legacy_plotly_adapter_adds_safe_export_and_diagnostics() -> None:
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    assert 'config.setdefault("displaylogo", False)' in theme
    assert '"format": "svg"' in theme
    assert "record_visual_error" in theme


def test_step109_version_is_synchronised() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text(encoding="utf-8")
