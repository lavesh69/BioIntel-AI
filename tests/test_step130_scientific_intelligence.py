from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import plotly.graph_objects as go

from biointel.nextgen.intelligence import (
    HANDOFF_TARGETS,
    add_evidence_items,
    audit_visuals,
    build_evidence_items,
    build_publication_bundle,
    build_scientific_story,
    compare_run_snapshots,
    create_handoff,
    evaluate_threshold_scenarios,
    list_evidence_board,
    list_handoffs,
    list_review_decisions,
    list_run_snapshots,
    list_scenarios,
    list_validation_cohorts,
    persist_run_snapshot,
    register_validation_cohort,
    save_review_decision,
    save_scenario_run,
)

ROOT = Path(__file__).resolve().parents[1]


def _paths(tmp: Path) -> tuple[Path, Path]:
    root = tmp / "project"
    root.mkdir(parents=True, exist_ok=True)
    return root, tmp / "state.sqlite3"


def test_step130_persistent_runs_and_comparison() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, db = _paths(Path(directory))
        result_a = pd.DataFrame({"candidate": ["A", "B"], "score": [0.8, 0.6]})
        result_b = pd.DataFrame({"candidate": ["A", "C", "D"], "score": [0.9, 0.7, 0.5]})
        id_a = persist_run_snapshot(
            project_root=root, module_key="digital_pathology_foundation", signature="a",
            parameters={"threshold": 0.7}, summary={"status": "ok"}, result=result_a,
            extras={"qc": result_a}, completed_at_utc="2026-07-11T01:00:00+00:00", path=db,
        )
        id_b = persist_run_snapshot(
            project_root=root, module_key="digital_pathology_foundation", signature="b",
            parameters={"threshold": 0.8}, summary={"status": "ok", "warning": "review"}, result=result_b,
            extras={"qc": result_b, "drift": result_b}, completed_at_utc="2026-07-11T02:00:00+00:00", path=db,
        )
        assert id_a != id_b
        runs = list_run_snapshots(root, "digital_pathology_foundation", path=db)
        assert len(runs) == 2
        comparison = compare_run_snapshots(runs.iloc[1].to_dict(), runs.iloc[0].to_dict())
        assert {"parameter", "result", "summary", "advanced_table"}.issubset(set(comparison["section"]))
        assert comparison["changed"].astype(bool).any()


def test_step130_evidence_review_handoff_and_cohorts() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, db = _paths(Path(directory))
        result = pd.DataFrame({"patient_id": ["P1", "P2"], "risk_score": [0.9, 0.6], "evidence_status": ["screening", "reference"]})
        items = build_evidence_items(module_key="clinical_biomarker_survival", result=result, run_id="RUN-1")
        assert len(items) == 2
        ids = add_evidence_items(project_root=root, board_id="board", items=items, path=db)
        assert len(ids) == 2
        assert len(list_evidence_board(root, "board", path=db)) == 2

        review_id = save_review_decision(
            project_root=root, module_key="clinical_biomarker_survival", entity_id="P1",
            decision="Shortlist", note="High risk score", reviewer="reviewer", run_id="RUN-1", path=db,
        )
        assert review_id.startswith("REV-")
        assert len(list_review_decisions(root, "clinical_biomarker_survival", path=db)) == 1

        handoff_id = create_handoff(
            project_root=root, source_module="clinical_biomarker_survival",
            target_module="synthetic_cohort_trial", payload={"patient": "P1"}, run_id="RUN-1", path=db,
        )
        assert handoff_id.startswith("HOF-")
        assert len(list_handoffs(root, target_module="synthetic_cohort_trial", path=db)) == 1

        cohort_id = register_validation_cohort(
            project_root=root, name="External cohort", module_key="clinical_biomarker_survival",
            cohort_role="external", source_bytes=b"patient,outcome\nP1,1\n", row_count=1,
            column_count=2, locked=True, blinded=False, notes="Independent site", path=db,
        )
        assert cohort_id.startswith("COH-")
        cohorts = list_validation_cohorts(root, path=db)
        assert len(cohorts) == 1
        assert int(cohorts.iloc[0]["locked"]) == 1


def test_step130_scenario_engine_and_persistence() -> None:
    data = pd.DataFrame({"candidate": ["A", "B", "C"], "score": [0.2, 0.7, 0.9]})

    def analyser(frame: pd.DataFrame, threshold: float):
        result = frame[frame["score"] >= threshold].copy()
        return result, {"threshold": threshold}, None, {"ranked": result}

    scenarios = evaluate_threshold_scenarios(data=data, analyser=analyser, thresholds=[0.3, 0.6, 0.8])
    assert scenarios["status"].eq("completed").all()
    assert scenarios["result_rows"].tolist() == [2, 2, 1]
    with tempfile.TemporaryDirectory() as directory:
        root, db = _paths(Path(directory))
        scenario_id = save_scenario_run(
            project_root=root, module_key="protein_ligand_codesign", name="Threshold test",
            baseline=0.7, results=scenarios, path=db,
        )
        assert scenario_id.startswith("SCN-")
        assert len(list_scenarios(root, "protein_ligand_codesign", path=db)) == 1


def test_step130_visual_audit_story_and_publication_bundle() -> None:
    frame = pd.DataFrame({"candidate": ["A", "B", "C"], "priority_score": [0.9, 0.8, 0.4]})
    figure = go.Figure(go.Bar(x=frame["candidate"], y=frame["priority_score"]))
    figure.update_layout(title="Candidate ranking", xaxis_title="Candidate", yaxis_title="Priority score")
    visual = SimpleNamespace(title="Candidate ranking", data=frame, figure=figure)
    audit = audit_visuals([visual])
    assert audit.iloc[0]["status"] == "Passed"

    story = build_scientific_story(
        module_title="Protein–Ligand Co-Design Studio", boundary="Research screening only",
        run_id="RUN-1", summary={"status": "ok"}, result=frame, extras={"pareto": frame},
    )
    assert len(story) == 6
    bundle = build_publication_bundle(
        module_key="protein_ligand_codesign", module_title="Protein–Ligand Co-Design Studio",
        boundary="Research screening only", run_id="RUN-1", result=frame,
        summary={"status": "ok"}, story=story, extras={"pareto": frame},
    )
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = set(archive.namelist())
        assert "figure/publication_figure.svg" in names
        assert "report/publication_report.pdf" in names
        assert "report/publication_report.docx" in names
        assert "report/publication_report.pptx" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["external_validation_claimed"] is False


def test_step130_ui_integration_and_release_contract() -> None:
    assert len(HANDOFF_TARGETS) == 15
    renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    workbench = (ROOT / "src/biointel/ui/workbench.py").read_text(encoding="utf-8")
    components = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    assert "render_nextgen_intelligence_workspace" in renderer
    assert "persist_run_snapshot" in workbench
    assert "publish_linked_selection" in components
    for page_number in range(189, 195):
        assert list((ROOT / "pages").glob(f"{page_number}_*.py")), page_number
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert (ROOT / "STEP130_RELEASE.json").exists()
    assert (ROOT / "config/step130_scientific_intelligence.json").exists()
