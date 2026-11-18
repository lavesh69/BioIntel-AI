from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from biointel.nextgen.interaction_v131 import (
    JOURNAL_PRESETS,
    add_review_comment,
    build_figure_layout_bundle,
    create_review_thread,
    get_viewer_sync_state,
    infer_uncertainty_columns,
    list_figure_layouts,
    list_review_comments,
    list_review_threads,
    list_selection_history,
    list_visual_provenance,
    progressive_sample,
    record_selection,
    save_figure_layout,
    save_viewer_sync_state,
    save_visual_provenance,
    uncertainty_profile,
    update_review_thread,
)

ROOT = Path(__file__).resolve().parents[1]


def _paths(tmp: Path) -> tuple[Path, Path]:
    root = tmp / "project"
    root.mkdir(parents=True, exist_ok=True)
    return root, tmp / "state.sqlite3"


def test_step131_progressive_sampling_preserves_selection_and_extrema() -> None:
    frame = pd.DataFrame({
        "candidate": [f"C{i}" for i in range(10000)],
        "score": list(range(10000)),
        "effect": [i % 97 for i in range(10000)],
    })
    sampled, manifest = progressive_sample(
        frame, limit=500, entity_column="candidate", score_column="score", selected_values=["C9999", "C1234"]
    )
    assert len(sampled) <= 500
    assert manifest.source_rows == 10000
    assert manifest.rendered_rows == len(sampled)
    assert {"C9999", "C1234"}.issubset(set(sampled["candidate"]))
    assert sampled["score"].max() == 9999
    assert sampled["score"].min() == 0


def test_step131_uncertainty_profile_detects_valid_intervals() -> None:
    frame = pd.DataFrame({
        "effect": [1.0, 2.0, 3.0],
        "effect_ci_low": [0.5, 1.5, 2.4],
        "effect_ci_high": [1.5, 2.5, 3.6],
    })
    pairs = infer_uncertainty_columns(frame)
    assert pairs == [{"estimate": "effect", "lower": "effect_ci_low", "upper": "effect_ci_high"}]
    profile = uncertainty_profile(frame)
    assert len(profile) == 1
    assert profile.iloc[0]["valid_intervals"] == 3
    assert profile.iloc[0]["estimate_inside_pct"] == 100.0


def test_step131_persistent_selection_provenance_and_sync() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, db = _paths(Path(directory))
        selection_id = record_selection(
            project_root=root, module_key="amr_surveillance", chart_key="amr_map",
            column_name="isolate_id", values=["I1", "I2"], path=db,
        )
        assert selection_id.startswith("SEL-")
        history = list_selection_history(root, "amr_surveillance", path=db)
        assert len(history) == 1
        assert history.iloc[0]["values"] == ["I1", "I2"]

        provenance_id = save_visual_provenance(
            project_root=root, module_key="amr_surveillance", run_id="RUN-1",
            chart_key="amr_map", entity_id="I1", source_row={"isolate_id": "I1", "score": 0.9},
            transformations={"threshold": 0.7}, figure_refs=["amr_map"], path=db,
        )
        assert provenance_id.startswith("PRV-")
        assert len(list_visual_provenance(root, "amr_surveillance", path=db)) == 1

        save_viewer_sync_state(
            project_root=root, module_key="amr_surveillance",
            state={"entity": "I1", "region": "ward-A", "zoom": 2.0}, path=db,
        )
        assert get_viewer_sync_state(root, "amr_surveillance", path=db)["zoom"] == 2.0


def test_step131_collaborative_review_and_figure_layout() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, db = _paths(Path(directory))
        thread_id = create_review_thread(
            project_root=root, module_key="clinical_biomarker_survival", run_id="RUN-1",
            entity_id="P1", title="Review high-risk patient", created_by="alice", assignee="bob", path=db,
        )
        comment_id = add_review_comment(
            project_root=root, thread_id=thread_id, author="bob", body="Verify external cohort evidence.",
            decision="Evidence requested", path=db,
        )
        assert thread_id.startswith("THR-") and comment_id.startswith("CMT-")
        assert update_review_thread(project_root=root, thread_id=thread_id, status="In review", path=db)
        threads = list_review_threads(root, "clinical_biomarker_survival", path=db)
        assert threads.iloc[0]["status"] == "In review"
        assert int(threads.iloc[0]["comment_count"]) == 1
        assert len(list_review_comments(root, thread_id, path=db)) == 1

        layout_id = save_figure_layout(
            project_root=root, module_key="clinical_biomarker_survival", run_id="RUN-1",
            name="Survival figure", preset="Nature two-column",
            panels=[{"title": "Kaplan–Meier", "values": [0.9, 0.7, 0.5]}], path=db,
        )
        assert layout_id.startswith("FIG-")
        layouts = list_figure_layouts(root, "clinical_biomarker_survival", path=db)
        assert len(layouts) == 1
        assert layouts.iloc[0]["dpi"] == JOURNAL_PRESETS["Nature two-column"]["dpi"]


def test_step131_layout_bundle_and_release_contract() -> None:
    bundle = build_figure_layout_bundle(
        module_key="protein_ligand_codesign", layout_name="Co-design figure",
        preset="Cell full-width", panels=[
            {"title": "Pareto frontier", "values": [0.2, 0.5, 0.9]},
            {"title": "Interaction score", "values": [1.0, 2.0, 3.0]},
        ], caption="Research figure", methods="Deterministic screening", boundary="Research use only",
    )
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = set(archive.namelist())
        assert "figure/figure_layout.svg" in names
        assert "figure/figure_layout.html" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["journal_acceptance_claimed"] is False
        assert len(manifest["panels"]) == 2

    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert (ROOT / "STEP131_RELEASE.json").exists()
    assert (ROOT / "config/step131_realtime_interaction_stability.json").exists()
    assert (ROOT / "pages/195_Real_Time_Scientific_Canvas_Collaboration_Center.py").exists()
    renderer = (ROOT / "src/biointel/ui/nextgen_intelligence.py").read_text(encoding="utf-8")
    workspace = (ROOT / "src/biointel/ui/reactive_scientific_workspace.py").read_text(encoding="utf-8")
    assert "render_reactive_scientific_workspace" in renderer
    assert "st.iframe(html_block" in workspace
    assert "st.html(html_block" not in workspace
    assert "progressive_sample" in workspace
